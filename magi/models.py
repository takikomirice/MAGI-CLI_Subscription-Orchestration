from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AdvisorPayload:
    summary: str
    approach: list[str] = field(default_factory=list)
    tradeoffs: list[dict[str, str]] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    recommended_next_steps: list[str] = field(default_factory=list)
    confidence: int = 0
    raw_output: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "approach": self.approach,
            "tradeoffs": self.tradeoffs,
            "risks": self.risks,
            "unknowns": self.unknowns,
            "recommended_next_steps": self.recommended_next_steps,
            "confidence": self.confidence,
            "raw_output": self.raw_output,
        }


@dataclass(slots=True)
class AdvisorResult:
    provider: str
    payload: AdvisorPayload
    prompt: str
    duration_seconds: float
    command: list[str] = field(default_factory=list)
    ok: bool = True
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "ok": self.ok,
            "error": self.error,
            "duration_seconds": round(self.duration_seconds, 3),
            "command": self.command,
            "prompt": self.prompt,
            "response": self.payload.as_dict(),
        }


@dataclass(slots=True)
class RunArtifacts:
    run_id: str
    run_dir: Path
    request_path: Path
    report_path: Path
    synthesis_path: Path
    advisor_paths: list[Path]
    synthesizer_path: Path | None = None


@dataclass(slots=True)
class HandoffContext:
    selector: str
    run_id: str
    mode: str
    run_dir: Path
    report_path: Path
    report_markdown: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "run_id": self.run_id,
            "mode": self.mode,
            "run_dir": str(self.run_dir),
            "report_path": str(self.report_path),
        }


@dataclass(slots=True)
class VerificationResult:
    command: list[str]
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "ok": self.ok,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": round(self.duration_seconds, 3),
            "timed_out": self.timed_out,
        }


@dataclass(slots=True)
class AgentAttempt:
    attempt: int
    prompt: str
    provider_result: AdvisorResult
    verification_results: list[VerificationResult] = field(default_factory=list)

    @property
    def verification_ok(self) -> bool:
        return bool(self.verification_results) and all(item.ok for item in self.verification_results)

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "prompt": self.prompt,
            "provider_result": self.provider_result.as_dict(),
            "verification_results": [item.as_dict() for item in self.verification_results],
            "verification_ok": self.verification_ok,
        }
