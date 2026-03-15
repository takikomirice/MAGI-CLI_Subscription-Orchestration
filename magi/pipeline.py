from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import time
from typing import Callable

from magi.cancellation import RunCancellation
from magi.config import AppConfig, ProviderConfig
from magi.io import ensure_dir, write_text, write_yaml
from magi.models import AgentAttempt, AdvisorPayload, AdvisorResult, RunArtifacts
from magi.prompts import build_mode_prompt, build_synthesis_report_prompt
from magi.providers.base import Provider
from magi.providers.external_cli import ExternalCLIProvider, run_text_prompt
from magi.providers.mock import MockProvider
from magi.runs import resolve_handoff_context
from magi.synthesis import build_synthesis, render_report
from magi.verification import run_verification_commands


ProgressCallback = Callable[[str], None]


def run_request(
    config: AppConfig,
    user_request: str,
    mode: str = "ask",
    selected_providers: set[str] | None = None,
    synth_provider: str | None = None,
    handoff_selector: str | None = None,
    model_overrides: dict[str, str] | None = None,
    effort_overrides: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
    cancellation: RunCancellation | None = None,
) -> RunArtifacts:
    run_id = _new_run_id(config.runs_dir)
    run_dir = config.runs_dir / run_id
    advisor_paths: list[Path] = []
    model_overrides = model_overrides or {}
    effort_overrides = effort_overrides or {}
    handoff = None

    _emit(progress, f"[{mode} 1/6] normalizing request")
    if handoff_selector:
        _emit(progress, f"[{mode}] resolving handoff {handoff_selector}")
        handoff = resolve_handoff_context(config.runs_dir, handoff_selector)
    ensure_dir(run_dir)

    write_yaml(
        run_dir / "request.yaml",
        {
            "run_id": run_id,
            "mode": mode,
            "project_name": config.project_name,
            "project_root": str(config.project_root),
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "user_request": user_request,
            "selected_providers": sorted(selected_providers) if selected_providers else [],
            "synth_provider": synth_provider or "",
            "handoff": handoff.as_dict() if handoff is not None else None,
            "model_overrides": model_overrides,
            "effort_overrides": effort_overrides,
        },
    )

    prompt = build_mode_prompt(
        mode,
        user_request,
        config.project_name,
        config.project_root,
        handoff=handoff,
    )
    providers = [
        item
        for item in config.providers
        if item.enabled and (not selected_providers or item.name in selected_providers)
    ]
    agent_loop = None
    if mode == "agent" and len(providers) == 1:
        attempts, results, advisor_paths, agent_loop = _run_agent_loop(
            config,
            providers[0],
            user_request,
            run_id,
            run_dir,
            handoff,
            model_overrides,
            effort_overrides,
            progress,
            cancellation,
        )
    else:
        if mode == "agent" and len(providers) > 1 and config.agent.verification_commands:
            _emit(
                progress,
                "[agent] verification loop skipped because agent mode currently supports one active provider at a time.",
            )
        results, advisor_paths = _consult_providers(
            providers,
            prompt,
            mode,
            run_dir,
            model_overrides,
            effort_overrides,
            progress,
            cancellation,
        )

    _emit(progress, f"[{mode} 5/6] synthesizing responses")
    synthesis = build_synthesis(results, user_request)
    synthesis["mode"] = mode
    synthesis["selected_providers"] = sorted(selected_providers) if selected_providers else []
    synthesis["synth_provider"] = synth_provider or ""
    synthesis["handoff"] = handoff.as_dict() if handoff is not None else None
    synthesis["agent_loop"] = agent_loop
    synthesis["model_overrides"] = model_overrides
    synthesis["effort_overrides"] = effort_overrides
    synthesis_path = run_dir / "synthesis.yaml"
    write_yaml(synthesis_path, synthesis)

    _emit(progress, f"[{mode} 6/6] writing report")
    report_path = run_dir / "report.md"
    synthesizer_path = run_dir / "synthesizer.yaml" if synth_provider else None
    report_text = _build_report_text(
        config,
        run_id,
        mode,
        user_request,
        results,
        synthesis,
        synth_provider,
        model_overrides,
        effort_overrides,
        synthesizer_path,
        progress,
        cancellation,
    )
    write_text(report_path, report_text)

    return RunArtifacts(
        run_id=run_id,
        run_dir=run_dir,
        request_path=run_dir / "request.yaml",
        report_path=report_path,
        synthesis_path=synthesis_path,
        advisor_paths=advisor_paths,
        synthesizer_path=synthesizer_path if synth_provider else None,
    )


def _run_agent_loop(
    config: AppConfig,
    provider_config: ProviderConfig,
    user_request: str,
    run_id: str,
    run_dir: Path,
    handoff,
    model_overrides: dict[str, str],
    effort_overrides: dict[str, str],
    progress: ProgressCallback | None,
    cancellation: RunCancellation | None,
) -> tuple[list[AgentAttempt], list[AdvisorResult], list[Path], dict[str, object]]:
    attempts: list[AgentAttempt] = []
    retry_feedback = ""
    provider_name = provider_config.name
    model = model_overrides.get(provider_name, "")
    effort = effort_overrides.get(provider_name, "")
    max_attempts = config.agent.max_attempts

    for attempt_number in range(1, max_attempts + 1):
        prompt = build_mode_prompt(
            "agent",
            user_request,
            config.project_name,
            config.project_root,
            handoff=handoff,
            retry_feedback=retry_feedback,
        )
        attempt_dir = run_dir / f"agent_attempt_{attempt_number:02d}"
        ensure_dir(attempt_dir)
        write_text(attempt_dir / "prompt.md", prompt)

        _emit(progress, f"[agent {attempt_number}/{max_attempts}] consulting {provider_name}")
        result = _run_provider_request(
            provider_config,
            prompt,
            model,
            effort,
            cancellation,
        )
        write_yaml(attempt_dir / "provider.yaml", result.as_dict())

        verification_results = []
        if result.ok and config.agent.verification_commands:
            _emit(progress, f"[agent {attempt_number}/{max_attempts}] running verification commands")
            verification_results = run_verification_commands(
                config.agent.verification_commands,
                config.project_root,
                run_id,
                attempt_number,
                config.agent.verification_timeout_seconds,
            )
            write_yaml(
                attempt_dir / "verification.yaml",
                [item.as_dict() for item in verification_results],
            )
        attempt = AgentAttempt(
            attempt=attempt_number,
            prompt=prompt,
            provider_result=result,
            verification_results=verification_results,
        )
        attempts.append(attempt)

        if cancellation is not None and cancellation.is_cancelled():
            break
        if not result.ok:
            break
        if not config.agent.verification_commands:
            break
        if attempt.verification_ok:
            _emit(progress, f"[agent] verification passed on attempt {attempt_number}")
            break
        if attempt_number >= max_attempts:
            _emit(progress, f"[agent] verification still failing after {attempt_number} attempt(s)")
            break
        retry_feedback = _build_verification_feedback(attempt)

    final_result = attempts[-1].provider_result if attempts else _provider_exception_result(
        provider_name,
        "",
        0.0,
        "Agent loop produced no provider attempts.",
    )
    advisor_path = run_dir / f"advisor_{provider_name}.yaml"
    write_yaml(advisor_path, final_result.as_dict())
    return attempts, [final_result], [advisor_path], _build_agent_loop_summary(config, attempts)


def build_provider(config: ProviderConfig) -> Provider:
    if config.type == "cli":
        return ExternalCLIProvider(config)
    return MockProvider(config.name)


def _consult_providers(
    providers: list[ProviderConfig],
    prompt: str,
    mode: str,
    run_dir: Path,
    model_overrides: dict[str, str],
    effort_overrides: dict[str, str],
    progress: ProgressCallback | None,
    cancellation: RunCancellation | None,
) -> tuple[list[AdvisorResult], list[Path]]:
    if not providers:
        return [], []

    results_by_provider: dict[str, AdvisorResult] = {}
    advisor_paths_by_provider: dict[str, Path] = {}

    with ThreadPoolExecutor(max_workers=len(providers), thread_name_prefix="magi-provider") as executor:
        futures = {}
        for index, provider_config in enumerate(providers, start=2):
            for warning in _command_template_warnings(
                provider_config,
                model_overrides.get(provider_config.name, ""),
                effort_overrides.get(provider_config.name, ""),
            ):
                _emit(progress, f"[warn] {warning}")
            _emit(progress, f"[{mode} {index}/6] consulting {provider_config.name}")
            future = executor.submit(
                _run_provider_request,
                provider_config,
                prompt,
                model_overrides.get(provider_config.name, ""),
                effort_overrides.get(provider_config.name, ""),
                cancellation,
            )
            futures[future] = provider_config

        for future in as_completed(futures):
            provider_config = futures[future]
            result = future.result()
            advisor_path = run_dir / f"advisor_{provider_config.name}.yaml"
            results_by_provider[provider_config.name] = result
            advisor_paths_by_provider[provider_config.name] = advisor_path
            write_yaml(advisor_path, result.as_dict())
            status = "completed" if result.ok else "cancelled" if cancellation is not None and result.error == cancellation.reason else "failed"
            _emit(progress, f"[{mode}] {status} {provider_config.name}")

    results = [results_by_provider[provider.name] for provider in providers]
    advisor_paths = [advisor_paths_by_provider[provider.name] for provider in providers]
    return results, advisor_paths


def _run_provider_request(
    provider_config: ProviderConfig,
    prompt: str,
    model: str,
    effort: str,
    cancellation: RunCancellation | None,
) -> AdvisorResult:
    start = time.perf_counter()
    try:
        provider = build_provider(provider_config)
        return provider.ask(prompt, model=model, effort=effort, cancellation=cancellation)
    except Exception as exc:
        return _provider_exception_result(
            provider_config.name,
            prompt,
            time.perf_counter() - start,
            str(exc),
        )


def _provider_exception_result(
    provider_name: str,
    prompt: str,
    duration_seconds: float,
    message: str,
) -> AdvisorResult:
    payload = AdvisorPayload(
        summary="Provider execution failed unexpectedly.",
        risks=[message],
        unknowns=["Review the provider logs or command output for the failing advisor."],
        recommended_next_steps=["Fix the provider failure and rerun the request."],
        confidence=0,
    )
    return AdvisorResult(
        provider=provider_name,
        payload=payload,
        prompt=prompt,
        duration_seconds=duration_seconds,
        ok=False,
        error=message,
    )


def _build_verification_feedback(attempt: AgentAttempt) -> str:
    lines = [
        f"Attempt {attempt.attempt} verification failed.",
        "",
    ]
    for index, result in enumerate(attempt.verification_results, start=1):
        if result.ok:
            continue
        command = " ".join(result.command) or "<empty command>"
        lines.append(f"{index}. command: {command}")
        lines.append(f"   exit_code: {result.exit_code}")
        if result.timed_out:
            lines.append("   timed_out: true")
        if result.stdout:
            lines.append("   stdout:")
            lines.append(_indent_block(_trim_output(result.stdout)))
        if result.stderr:
            lines.append("   stderr:")
            lines.append(_indent_block(_trim_output(result.stderr)))
        lines.append("")
    return "\n".join(lines).strip()


def _build_agent_loop_summary(config: AppConfig, attempts: list[AgentAttempt]) -> dict[str, object]:
    if not attempts:
        return {
            "enabled": True,
            "attempts": 0,
            "max_attempts": config.agent.max_attempts,
            "verification_commands": config.agent.verification_commands,
            "verification_configured": bool(config.agent.verification_commands),
            "verification_passed": False,
            "failed_attempts": [],
        }

    final_attempt = attempts[-1]
    verification_configured = bool(config.agent.verification_commands)
    return {
        "enabled": True,
        "attempts": len(attempts),
        "max_attempts": config.agent.max_attempts,
        "verification_commands": config.agent.verification_commands,
        "verification_configured": verification_configured,
        "verification_passed": final_attempt.verification_ok if verification_configured else False,
        "failed_attempts": [
            {
                "attempt": attempt.attempt,
                "provider_ok": attempt.provider_result.ok,
                "verification_failures": [
                    item.as_dict() for item in attempt.verification_results if not item.ok
                ],
            }
            for attempt in attempts
            if (not attempt.provider_result.ok) or any(not item.ok for item in attempt.verification_results)
        ],
    }


def _trim_output(text: str, limit: int = 4000) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit].rstrip() + "\n...[truncated]"


def _indent_block(text: str) -> str:
    return "\n".join(f"     {line}" for line in text.splitlines())


def _new_run_id(runs_dir: Path) -> str:
    ensure_dir(runs_dir)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    suffix = 1
    while True:
        candidate = f"{stamp}-{suffix:03d}"
        if not (runs_dir / candidate).exists():
            return candidate
        suffix += 1


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _command_template_warnings(
    config: ProviderConfig,
    model_override: str,
    effort_override: str,
) -> list[str]:
    if config.type != "cli" or not config.command:
        return []

    template = " ".join(config.command)
    warnings: list[str] = []

    if model_override and "{model}" not in template:
        warnings.append(
            f"{config.name}: command template does not include {{model}}; model selection will not be passed to the CLI."
        )
    if effort_override and "{effort}" not in template:
        warnings.append(
            f"{config.name}: command template does not include {{effort}}; effort selection will not be passed to the CLI."
        )

    return warnings


def _build_report_text(
    config: AppConfig,
    run_id: str,
    mode: str,
    user_request: str,
    results: list[AdvisorResult],
    synthesis: dict[str, object],
    synth_provider: str | None,
    model_overrides: dict[str, str],
    effort_overrides: dict[str, str],
    synthesizer_path: Path | None,
    progress: ProgressCallback | None,
    cancellation: RunCancellation | None,
) -> str:
    if cancellation is not None and cancellation.is_cancelled():
        synthesis["synth_error"] = cancellation.reason
        return render_report(run_id, synthesis, results)

    if not synth_provider:
        return render_report(run_id, synthesis, results)

    provider_config = _find_provider_config(config, synth_provider)
    if provider_config is None:
        synthesis["synth_error"] = f"Unknown synthesizer provider: {synth_provider}"
        return render_report(run_id, synthesis, results)

    if provider_config.name not in {result.provider for result in results if result.ok}:
        synthesis["synth_error"] = f"Synthesizer provider was not active in this run: {synth_provider}"
        return render_report(run_id, synthesis, results)

    if provider_config.type != "cli":
        synthesis["synth_note"] = f"{synth_provider} selected as synthesizer, but provider type is {provider_config.type}; using heuristic report."
        return render_report(run_id, synthesis, results)

    _emit(progress, f"[{mode}] requesting final synthesis from {synth_provider}")
    synth_prompt = build_synthesis_report_prompt(
        user_request,
        mode,
        config.project_name,
        config.project_root,
        [result.as_dict() for result in results],
        synthesis,
    )
    command_result = run_text_prompt(
        provider_config,
        synth_prompt,
        model=model_overrides.get(synth_provider, ""),
        effort=effort_overrides.get(synth_provider, ""),
        cancellation=cancellation,
    )
    if synthesizer_path is not None:
        write_yaml(
            synthesizer_path,
            {
                "provider": synth_provider,
                "ok": command_result.ok,
                "command": command_result.command,
                "duration_seconds": round(command_result.duration_seconds, 3),
                "error": command_result.stderr,
                "output": command_result.stdout,
            },
        )

    if command_result.cancelled:
        synthesis["synth_error"] = command_result.stderr or (cancellation.reason if cancellation else "Cancelled by user.")
        return render_report(run_id, synthesis, results)

    if not command_result.ok or not command_result.stdout.strip():
        synthesis["synth_error"] = command_result.stderr or "Synthesizer returned no output."
        return render_report(run_id, synthesis, results)

    return _wrap_synthesized_report(run_id, mode, synthesis, synth_provider, command_result.stdout)


def _wrap_synthesized_report(
    run_id: str,
    mode: str,
    synthesis: dict[str, object],
    synth_provider: str,
    markdown: str,
) -> str:
    lines = [
        "# MAGI Report",
        "",
        f"- run_id: `{run_id}`",
        f"- mode: `{mode}`",
        f"- synthesizer: `{synth_provider}`",
        f"- successful_providers: {', '.join(synthesis['successful_providers']) or 'none'}",
        "",
        markdown.strip(),
        "",
    ]
    return "\n".join(lines)


def _find_provider_config(config: AppConfig, provider_name: str) -> ProviderConfig | None:
    for provider in config.providers:
        if provider.name == provider_name:
            return provider
    return None
