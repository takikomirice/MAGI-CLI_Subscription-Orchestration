from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from magi.models import VerificationResult


def run_verification_commands(
    commands: list[list[str]],
    project_root: Path,
    run_id: str,
    attempt: int,
    timeout_seconds: int,
) -> list[VerificationResult]:
    results: list[VerificationResult] = []
    for template in commands:
        command = [
            part.format(
                project_root=str(project_root),
                run_id=run_id,
                attempt=attempt,
            )
            for part in template
        ]
        results.append(
            _run_verification_command(
                command,
                project_root,
                run_id,
                attempt,
                timeout_seconds,
            )
        )
    return results


def _run_verification_command(
    command: list[str],
    project_root: Path,
    run_id: str,
    attempt: int,
    timeout_seconds: int,
) -> VerificationResult:
    start = time.perf_counter()
    if not command:
        return VerificationResult(
            command=[],
            ok=False,
            exit_code=-1,
            stdout="",
            stderr="Empty verification command.",
            duration_seconds=0.0,
        )

    resolved = list(command)
    executable = shutil.which(resolved[0])
    if executable is not None:
        resolved[0] = executable

    env = os.environ.copy()
    env["MAGI_AGENT_ATTEMPT"] = str(attempt)
    env["MAGI_RUN_ID"] = run_id
    env["MAGI_PROJECT_ROOT"] = str(project_root)

    try:
        completed = subprocess.run(
            resolved,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        return VerificationResult(
            command=resolved,
            ok=False,
            exit_code=-1,
            stdout="",
            stderr=str(exc),
            duration_seconds=time.perf_counter() - start,
        )
    except subprocess.TimeoutExpired as exc:
        return VerificationResult(
            command=resolved,
            ok=False,
            exit_code=-1,
            stdout=(exc.stdout or "").strip(),
            stderr=((exc.stderr or "").strip() or f"Timed out after {timeout_seconds} seconds."),
            duration_seconds=time.perf_counter() - start,
            timed_out=True,
        )

    return VerificationResult(
        command=resolved,
        ok=completed.returncode == 0,
        exit_code=completed.returncode,
        stdout=(completed.stdout or "").strip(),
        stderr=(completed.stderr or "").strip(),
        duration_seconds=time.perf_counter() - start,
        timed_out=False,
    )
