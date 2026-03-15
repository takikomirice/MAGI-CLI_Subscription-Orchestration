from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass

from magi.cancellation import RunCancellation, terminate_process_tree
from magi.config import ProviderConfig
from magi.models import AdvisorPayload, AdvisorResult
from magi.providers.base import Provider


@dataclass(slots=True)
class CommandRunResult:
    command: list[str]
    ok: bool
    stdout: str
    stderr: str
    duration_seconds: float
    cancelled: bool = False


class ExternalCLIProvider(Provider):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def ask(
        self,
        prompt: str,
        model: str = "",
        effort: str = "",
        cancellation: RunCancellation | None = None,
    ) -> AdvisorResult:
        result = run_text_prompt(self.config, prompt, model=model, effort=effort, cancellation=cancellation)
        if not result.command:
            return self._error_result(prompt, [], "No command configured.", result.duration_seconds)
        if result.cancelled:
            return self._cancelled_result(
                prompt,
                result.command,
                result.stderr or "Provider execution cancelled.",
                result.duration_seconds,
            )
        if not result.ok:
            return self._error_result(
                prompt,
                result.command,
                result.stderr or "Provider execution failed.",
                result.duration_seconds,
                stdout=result.stdout,
            )

        payload = _parse_payload(result.stdout)
        return AdvisorResult(
            provider=self.config.name,
            payload=payload,
            prompt=prompt,
            duration_seconds=result.duration_seconds,
            command=result.command,
            ok=True,
            error=result.stderr,
        )

    def _cancelled_result(
        self,
        prompt: str,
        command: list[str],
        message: str,
        duration_seconds: float,
    ) -> AdvisorResult:
        payload = AdvisorPayload(
            summary="Provider execution cancelled.",
            risks=[message],
            unknowns=["The advisor did not complete because the MAGI run was cancelled."],
            recommended_next_steps=["Retry the request when you want to continue."],
            confidence=0,
        )
        return AdvisorResult(
            provider=self.config.name,
            payload=payload,
            prompt=prompt,
            duration_seconds=duration_seconds,
            command=command,
            ok=False,
            error=message,
        )

    def _error_result(
        self,
        prompt: str,
        command: list[str],
        message: str,
        duration_seconds: float,
        stdout: str = "",
    ) -> AdvisorResult:
        payload = AdvisorPayload(
            summary="Provider execution failed.",
            risks=[message],
            unknowns=["Review the provider command and local CLI installation."],
            recommended_next_steps=["Fix the provider configuration and rerun the request."],
            confidence=0,
            raw_output=stdout,
        )
        return AdvisorResult(
            provider=self.config.name,
            payload=payload,
            prompt=prompt,
            duration_seconds=duration_seconds,
            command=command,
            ok=False,
            error=message,
        )


def run_text_prompt(
    config: ProviderConfig,
    prompt: str,
    model: str = "",
    effort: str = "",
    cancellation: RunCancellation | None = None,
) -> CommandRunResult:
    start = time.perf_counter()
    resolved_model = model or config.default_model
    resolved_effort = effort or config.default_effort
    command = [
        part.format(prompt=prompt, model=resolved_model, effort=resolved_effort)
        for part in config.command
    ]
    executable = command[0] if command else ""
    resolved_executable = shutil.which(executable) if executable else None

    if not command:
        return CommandRunResult(command=[], ok=False, stdout="", stderr="No command configured.", duration_seconds=0.0)
    if resolved_executable is None:
        return CommandRunResult(
            command=command,
            ok=False,
            stdout="",
            stderr=f"Executable not found on PATH: {executable}",
            duration_seconds=time.perf_counter() - start,
        )
    command[0] = resolved_executable
    if cancellation is not None and cancellation.is_cancelled():
        return CommandRunResult(
            command=command,
            ok=False,
            stdout="",
            stderr=cancellation.reason,
            duration_seconds=time.perf_counter() - start,
            cancelled=True,
        )

    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if config.stdin_prompt else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if cancellation is not None and not cancellation.register_process(process):
            stdout, stderr = _collect_output_after_cancel(process)
            return CommandRunResult(
                command=command,
                ok=False,
                stdout=stdout,
                stderr=cancellation.reason,
                duration_seconds=time.perf_counter() - start,
                cancelled=True,
            )
        if config.stdin_prompt and process.stdin is not None:
            process.stdin.write(prompt)
            process.stdin.close()
        deadline = start + config.timeout_seconds
        while True:
            if cancellation is not None and cancellation.is_cancelled():
                stdout, stderr = _cancel_running_process(process, cancellation.reason)
                return CommandRunResult(
                    command=command,
                    ok=False,
                    stdout=stdout,
                    stderr=cancellation.reason or stderr,
                    duration_seconds=time.perf_counter() - start,
                    cancelled=True,
                )
            try:
                stdout, stderr = process.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                if time.perf_counter() >= deadline:
                    stdout, stderr = _cancel_running_process(
                        process,
                        f"Timed out after {config.timeout_seconds} seconds.",
                    )
                    return CommandRunResult(
                        command=command,
                        ok=False,
                        stdout=stdout,
                        stderr=f"Timed out after {config.timeout_seconds} seconds.",
                        duration_seconds=time.perf_counter() - start,
                    )
                continue
    except OSError as exc:
        return CommandRunResult(
            command=command,
            ok=False,
            stdout="",
            stderr=str(exc),
            duration_seconds=time.perf_counter() - start,
        )
    finally:
        if cancellation is not None:
            cancellation.unregister_process(process)

    return CommandRunResult(
        command=command,
        ok=process.returncode == 0,
        stdout=(stdout or "").strip(),
        stderr=(stderr or "").strip() or ("" if process.returncode == 0 else f"Provider exited with code {process.returncode}."),
        duration_seconds=time.perf_counter() - start,
    )


def _cancel_running_process(process: subprocess.Popen[str], message: str) -> tuple[str, str]:
    process.poll()
    if process.returncode is None:
        terminate_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=1)
            return stdout, stderr
        except subprocess.TimeoutExpired:
            pass
    return _collect_output_after_cancel(process)


def _collect_output_after_cancel(process: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        stdout, stderr = process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        stdout, stderr = "", ""
    return stdout, stderr


def _parse_payload(stdout: str) -> AdvisorPayload:
    raw = _load_json_payload(stdout)
    if raw is None:
        return _fallback_payload(stdout)

    return AdvisorPayload(
        summary=str(raw.get("summary") or "No summary returned."),
        approach=[str(item) for item in raw.get("approach", [])],
        tradeoffs=[
            {
                "pro": str(item.get("pro", "")),
                "con": str(item.get("con", "")),
            }
            for item in raw.get("tradeoffs", [])
            if isinstance(item, dict)
        ],
        risks=[str(item) for item in raw.get("risks", [])],
        unknowns=[str(item) for item in raw.get("unknowns", [])],
        recommended_next_steps=[
            str(item) for item in raw.get("recommended_next_steps", [])
        ],
        confidence=_normalize_confidence(raw.get("confidence", 0)),
        raw_output=stdout,
    )


def _load_json_payload(stdout: str) -> dict[str, object] | None:
    candidates = [stdout.strip()]

    fenced = _strip_code_fence(stdout)
    if fenced and fenced not in candidates:
        candidates.append(fenced)

    extracted = _extract_braced_json(stdout)
    if extracted and extracted not in candidates:
        candidates.append(extracted)

    if fenced:
        extracted_fenced = _extract_braced_json(fenced)
        if extracted_fenced and extracted_fenced not in candidates:
            candidates.append(extracted_fenced)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _strip_code_fence(text: str) -> str:
    match = re.match(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()


def _extract_braced_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start : end + 1].strip()


def _fallback_payload(stdout: str) -> AdvisorPayload:
    lines = [line.strip("- ").strip() for line in stdout.splitlines() if line.strip()]
    summary = lines[0] if lines else "Provider returned no usable output."
    approach = lines[1:4]
    unknowns = []
    if stdout:
        unknowns.append("Provider output was not JSON; inspect raw_output before automating.")
    return AdvisorPayload(
        summary=summary,
        approach=approach,
        risks=[],
        unknowns=unknowns,
        recommended_next_steps=["Update the provider prompt so it returns machine-readable JSON."],
        confidence=40 if stdout else 0,
        raw_output=stdout,
    )


def _normalize_confidence(value: object) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0

    if 0.0 <= numeric <= 1.0:
        numeric *= 100
    return max(0, min(100, round(numeric)))
