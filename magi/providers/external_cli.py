from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass

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


class ExternalCLIProvider(Provider):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def ask(self, prompt: str, model: str = "", effort: str = "") -> AdvisorResult:
        result = run_text_prompt(self.config, prompt, model=model, effort=effort)
        if not result.command:
            return self._error_result(prompt, [], "No command configured.", result.duration_seconds)
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

    try:
        completed = subprocess.run(
            command,
            input=prompt if config.stdin_prompt else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.timeout_seconds,
            check=False,
        )
    except OSError as exc:
        return CommandRunResult(
            command=command,
            ok=False,
            stdout="",
            stderr=str(exc),
            duration_seconds=time.perf_counter() - start,
        )
    except subprocess.TimeoutExpired:
        return CommandRunResult(
            command=command,
            ok=False,
            stdout="",
            stderr=f"Timed out after {config.timeout_seconds} seconds.",
            duration_seconds=time.perf_counter() - start,
        )

    return CommandRunResult(
        command=command,
        ok=completed.returncode == 0,
        stdout=(completed.stdout or "").strip(),
        stderr=(completed.stderr or "").strip() or ("" if completed.returncode == 0 else f"Provider exited with code {completed.returncode}."),
        duration_seconds=time.perf_counter() - start,
    )


def _parse_payload(stdout: str) -> AdvisorPayload:
    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError:
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
