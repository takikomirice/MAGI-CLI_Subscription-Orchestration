from __future__ import annotations

import time

from magi.models import AdvisorPayload, AdvisorResult
from magi.providers.base import Provider


class MockProvider(Provider):
    def __init__(self, name: str) -> None:
        self.name = name

    def ask(self, prompt: str, model: str = "", effort: str = "") -> AdvisorResult:
        start = time.perf_counter()
        mode = self._extract_mode(prompt)
        snippet = prompt.strip().splitlines()[-1][:80]
        suffix_parts = []
        if model:
            suffix_parts.append(f"model={model}")
        if effort:
            suffix_parts.append(f"effort={effort}")
        detail_suffix = f" [{' | '.join(suffix_parts)}]" if suffix_parts else ""
        payload = AdvisorPayload(
            summary=self._summary(mode, snippet) + detail_suffix,
            approach=self._approach(mode),
            tradeoffs=self._tradeoffs(mode),
            risks=self._risks(mode),
            unknowns=self._unknowns(mode),
            recommended_next_steps=self._next_steps(mode),
            confidence=self._confidence(mode),
            raw_output=f"mock-response:{self.name}:{mode}:{model or 'default'}:{effort or 'default'}",
        )
        command = ["mock"]
        if model:
            command.extend(["--model", model])
        if effort:
            command.extend(["--effort", effort])
        return AdvisorResult(
            provider=self.name,
            payload=payload,
            prompt=prompt,
            duration_seconds=time.perf_counter() - start,
            command=command,
            ok=True,
        )

    def _extract_mode(self, prompt: str) -> str:
        for line in prompt.splitlines():
            if line.lower().startswith("current mode:"):
                return line.split(":", 1)[1].strip().lower()
        return "ask"

    def _summary(self, mode: str, snippet: str) -> str:
        if mode == "plan":
            summaries = {
                "codex": f"Sequence the MVP so provider adapters, run persistence, and reporting land before advanced orchestration. Request focus: {snippet}",
                "claude": f"Plan around readable outputs and minimal scope so the first release stays easy to evaluate. Request focus: {snippet}",
                "gemini": f"Use a staged rollout that keeps disagreement tracking from the first version without adding workers yet. Request focus: {snippet}",
            }
            return summaries.get(self.name, f"Provide a compact planning answer for: {snippet}")
        if mode == "debug":
            summaries = {
                "codex": f"Treat the issue as an interface or parsing failure first, then narrow toward provider-specific behavior. Request focus: {snippet}",
                "claude": f"Debug from observable outputs and failure surfaces before changing abstractions. Request focus: {snippet}",
                "gemini": f"Prioritize reproducibility and missing signals so advisor disagreements are easier to interpret. Request focus: {snippet}",
            }
            return summaries.get(self.name, f"Provide a compact debugging answer for: {snippet}")
        if mode == "agent":
            summaries = {
                "codex": f"Define lean agent roles with explicit boundaries instead of building a deep worker hierarchy. Request focus: {snippet}",
                "claude": f"Keep agent coordination review-heavy so humans stay in control of execution decisions. Request focus: {snippet}",
                "gemini": f"Use agents mainly for structured handoffs and preserving minority opinions in planning. Request focus: {snippet}",
            }
            return summaries.get(self.name, f"Provide a compact agent answer for: {snippet}")
        summaries = {
            "codex": f"Build a minimal, auditable CLI workflow first and keep the provider boundary thin. Request focus: {snippet}",
            "claude": f"Prioritize a readable report and stable response schema before adding agent coordination. Request focus: {snippet}",
            "gemini": f"Start from a structured advisory meeting pattern and preserve minority opinions in the output. Request focus: {snippet}",
        }
        return summaries.get(self.name, f"Provide a compact advisory answer for: {snippet}")

    def _approach(self, mode: str) -> list[str]:
        shared_by_mode = {
            "ask": [
                "Use one shared response schema for every advisor.",
                "Persist every run to files for auditability.",
            ],
            "plan": [
                "Sequence the MVP so the shortest useful path lands first.",
                "Keep provider abstraction thin until real CLI differences are known.",
            ],
            "debug": [
                "Reproduce the failure in the smallest possible path first.",
                "Inspect raw provider output before changing the parser.",
            ],
            "agent": [
                "Define explicit roles, ownership, and handoff points.",
                "Keep execution optional and review-centered in the first version.",
            ],
        }
        specifics = {
            "ask": {
                "codex": ["Implement provider adapters before advanced orchestration."],
                "claude": ["Optimize the final report for human review, not agent autonomy."],
                "gemini": ["Keep disagreement visible instead of forcing full consensus."],
            },
            "plan": {
                "codex": ["Ship one-shot execution before adding the interactive shell extras."],
                "claude": ["Write the report contract before broadening the command surface."],
                "gemini": ["Stage future local-LLM support behind the provider interface."],
            },
            "debug": {
                "codex": ["Check command invocation and stdout parsing before touching synthesis."],
                "claude": ["Use the report and advisor YAML files to compare where behavior diverges."],
                "gemini": ["Log the exact prompt and provider response that produced the failure."],
            },
            "agent": {
                "codex": ["Treat /agent as planning-first until worker execution is justified."],
                "claude": ["Route final approval through a reviewer step instead of trusting agents blindly."],
                "gemini": ["Preserve minority recommendations even when one lead agent proposes the main path."],
            },
        }
        return shared_by_mode.get(mode, shared_by_mode["ask"]) + specifics.get(mode, specifics["ask"]).get(self.name, [])

    def _tradeoffs(self, mode: str) -> list[dict[str, str]]:
        tradeoffs = {
            "ask": {
                "pro": "A thin MVP is easy to reason about and debug.",
                "con": "It will not yet automate re-ask or worker delegation.",
            },
            "plan": {
                "pro": "A staged rollout keeps delivery speed high.",
                "con": "Some future-facing abstractions stay intentionally unfinished.",
            },
            "debug": {
                "pro": "A narrow repro path makes failures easier to isolate.",
                "con": "It may postpone broader refactors until the cause is clearer.",
            },
            "agent": {
                "pro": "Planning agent roles first avoids premature orchestration complexity.",
                "con": "The first release will not feel fully autonomous yet.",
            },
        }
        return [tradeoffs.get(mode, tradeoffs["ask"])]

    def _risks(self, mode: str) -> list[str]:
        risks = {
            "ask": [
                "Real CLI invocation formats will vary by installed environment.",
                "Over-designing provider abstraction too early can slow delivery.",
            ],
            "plan": [
                "Adding every desired mode feature in v1 can blur the core value.",
                "Planning beyond known CLI behavior may create unnecessary abstractions.",
            ],
            "debug": [
                "A parser failure can hide the real provider response if raw output is not saved.",
                "Shell encoding issues can look like model or adapter bugs.",
            ],
            "agent": [
                "Execution-oriented agent mode can explode scope if workers are added too early.",
                "Role overlap can make synthesis noisy if boundaries stay vague.",
            ],
        }
        return risks.get(mode, risks["ask"])

    def _unknowns(self, mode: str) -> list[str]:
        unknowns = {
            "ask": [
                "Which CLI flags are stable across local installations?",
                "How strict should the response parser be for real provider output?",
            ],
            "plan": [
                "How many modes can the shell support before discoverability drops?",
                "Which features belong in MVP versus the first extension pass?",
            ],
            "debug": [
                "Is the failure in provider execution, parsing, or synthesis?",
                "What raw output did the provider produce before the error surfaced?",
            ],
            "agent": [
                "Should /agent stay planning-only or eventually launch workers?",
                "What review step should gate any future automated execution?",
            ],
        }
        return unknowns.get(mode, unknowns["ask"])

    def _next_steps(self, mode: str) -> list[str]:
        next_steps = {
            "ask": [
                "Verify the end-to-end flow with mock providers first.",
                "Configure each real CLI command in a project-local config file.",
            ],
            "plan": [
                "Implement the shell and mode persistence before adding advanced commands.",
                "Keep quota display as placeholders until provider-specific usage parsing exists.",
            ],
            "debug": [
                "Capture raw provider output alongside parsed fields for every run.",
                "Reproduce failures through the smallest command path first.",
            ],
            "agent": [
                "Define role templates and handoff structure before any worker execution.",
                "Keep /agent as advisory orchestration in the first release.",
            ],
        }
        specifics = {
            "ask": {
                "codex": ["Add run-level metadata before implementing diff refinement."],
                "claude": ["Refine the advisor prompt so the report reads well for humans."],
                "gemini": ["Define how disagreement should surface in the synthesis report."],
            },
            "plan": {
                "codex": ["Pin the minimal file structure before touching provider-specific optimizations."],
                "claude": ["Document the shell command semantics before expanding the REPL."],
                "gemini": ["Leave local LLM and SLM providers for the next version boundary."],
            },
            "debug": {
                "codex": ["Compare stdout and stderr handling across providers."],
                "claude": ["Review the saved YAML before assuming the shell state machine is wrong."],
                "gemini": ["Test encoding behavior in both one-shot and interactive paths."],
            },
            "agent": {
                "codex": ["Add role presets before adding any background execution."],
                "claude": ["Require reviewer confirmation for any future agent-generated plan."],
                "gemini": ["Keep dissent visible inside agent-mode synthesis output."],
            },
        }
        return next_steps.get(mode, next_steps["ask"]) + specifics.get(mode, specifics["ask"]).get(self.name, [])

    def _confidence(self, mode: str) -> int:
        offsets = {"ask": 0, "plan": 3, "debug": 2, "agent": 1}
        scores = {"codex": 83, "claude": 81, "gemini": 79}
        return min(scores.get(self.name, 75) + offsets.get(mode, 0), 95)
