from __future__ import annotations

from collections import Counter

from magi.models import AdvisorResult


def build_synthesis(results: list[AdvisorResult], user_request: str) -> dict[str, object]:
    successful = [result for result in results if result.ok]
    failed = [result for result in results if not result.ok]

    agreement = _shared_items(
        successful,
        lambda result: (
            result.payload.approach
            + result.payload.risks
            + result.payload.recommended_next_steps
        ),
    )
    open_questions = _shared_items(successful, lambda result: result.payload.unknowns, minimum=1)
    recommended = _shared_items(successful, lambda result: result.payload.recommended_next_steps, minimum=1)

    differences = []
    for result in successful:
        differences.append(
            {
                "provider": result.provider,
                "summary": result.payload.summary,
                "distinct_approach": _distinct_items(result, successful, "approach"),
                "distinct_risks": _distinct_items(result, successful, "risks"),
            }
        )

    return {
        "request": user_request,
        "successful_providers": [result.provider for result in successful],
        "failed_providers": [
            {"provider": result.provider, "error": result.error}
            for result in failed
        ],
        "agreement": agreement[:8],
        "open_questions": open_questions[:8],
        "recommended_next_steps": recommended[:8],
        "differences": differences,
    }


def render_report(run_id: str, synthesis: dict[str, object], results: list[AdvisorResult]) -> str:
    mode = str(synthesis.get("mode") or "ask")
    lines = [
        "# MAGI Report",
        "",
        f"- run_id: `{run_id}`",
        f"- mode: `{mode}`",
        f"- successful_providers: {', '.join(synthesis['successful_providers']) or 'none'}",
    ]
    synth_provider = str(synthesis.get("synth_provider") or "").strip()
    if synth_provider:
        lines.append(f"- synthesizer: `{synth_provider}`")

    failed = synthesis["failed_providers"]
    if failed:
        lines.append(
            "- failed_providers: "
            + ", ".join(item["provider"] for item in failed)
        )
    synth_note = str(synthesis.get("synth_note") or "").strip()
    if synth_note:
        lines.append(f"- synth_note: {synth_note}")
    synth_error = str(synthesis.get("synth_error") or "").strip()
    if synth_error:
        lines.append(f"- synth_error: {synth_error}")
    agent_loop = synthesis.get("agent_loop")
    if isinstance(agent_loop, dict) and agent_loop.get("enabled"):
        lines.append(f"- agent_attempts: {agent_loop.get('attempts', 0)}/{agent_loop.get('max_attempts', 0)}")
        if agent_loop.get("verification_configured"):
            verification_state = "passed" if agent_loop.get("verification_passed") else "failed"
            lines.append(f"- agent_verification: {verification_state}")
        else:
            lines.append("- agent_verification: not configured")

    lines.extend(
        [
            "",
            "## Request",
            "",
            str(synthesis["request"]),
            "",
            "## Agreement",
            "",
        ]
    )

    agreement = synthesis["agreement"]
    if agreement:
        lines.extend(f"- {item}" for item in agreement)
    else:
        lines.append("- No strong overlap was detected in this pass.")

    lines.extend(["", "## Differences", ""])
    for item in synthesis["differences"]:
        lines.append(f"### {item['provider']}")
        lines.append("")
        lines.append(item["summary"])
        lines.append("")
        distinct_approach = item["distinct_approach"]
        if distinct_approach:
            lines.append("Distinct approach points:")
            lines.extend(f"- {entry}" for entry in distinct_approach)
            lines.append("")
        distinct_risks = item["distinct_risks"]
        if distinct_risks:
            lines.append("Distinct risks:")
            lines.extend(f"- {entry}" for entry in distinct_risks)
            lines.append("")

    lines.extend(["## Open Questions", ""])
    open_questions = synthesis["open_questions"]
    if open_questions:
        lines.extend(f"- {item}" for item in open_questions)
    else:
        lines.append("- None surfaced explicitly.")

    lines.extend(["", "## Recommended Next Steps", ""])
    next_steps = synthesis["recommended_next_steps"]
    if next_steps:
        lines.extend(f"- {item}" for item in next_steps)
    else:
        lines.append("- Review the advisor YAML files and refine the prompt for a second pass.")

    lines.extend(["", "## Advisor Confidence", ""])
    for result in results:
        status = "ok" if result.ok else "failed"
        lines.append(
            f"- {result.provider}: {status}, confidence={result.payload.confidence}, duration={result.duration_seconds:.2f}s"
        )

    if isinstance(agent_loop, dict) and agent_loop.get("enabled"):
        lines.extend(["", "## Agent Loop", ""])
        attempts = int(agent_loop.get("attempts", 0))
        max_attempts = int(agent_loop.get("max_attempts", 0))
        lines.append(f"- attempts: {attempts}/{max_attempts}")
        if agent_loop.get("verification_configured"):
            verification_state = "passed" if agent_loop.get("verification_passed") else "failed"
            lines.append(f"- verification: {verification_state}")
            commands = agent_loop.get("verification_commands") or []
            if commands:
                lines.append("- commands:")
                lines.extend(f"  - {' '.join(command)}" for command in commands)
        else:
            lines.append("- verification: not configured")
        failed_attempts = agent_loop.get("failed_attempts") or []
        if failed_attempts:
            lines.append("- failed_attempts:")
            for item in failed_attempts:
                lines.append(f"  - attempt {item['attempt']}: provider_ok={item['provider_ok']}")
                for failure in item.get("verification_failures", []):
                    lines.append(
                        f"    - {' '.join(failure['command']) or '<empty command>'} -> exit {failure['exit_code']}"
                    )

    return "\n".join(lines).strip() + "\n"


def _shared_items(
    results: list[AdvisorResult],
    extractor,
    minimum: int = 2,
) -> list[str]:
    counter: Counter[str] = Counter()
    original: dict[str, str] = {}
    for result in results:
        seen = set()
        for item in extractor(result):
            token = _normalize(item)
            if not token or token in seen:
                continue
            seen.add(token)
            counter[token] += 1
            original.setdefault(token, item)
    ranked = [
        original[token]
        for token, count in counter.most_common()
        if count >= minimum
    ]
    return ranked


def _distinct_items(
    target: AdvisorResult,
    results: list[AdvisorResult],
    field_name: str,
) -> list[str]:
    others = set()
    for result in results:
        if result.provider == target.provider:
            continue
        for item in getattr(result.payload, field_name):
            token = _normalize(item)
            if token:
                others.add(token)
    output = []
    for item in getattr(target.payload, field_name):
        token = _normalize(item)
        if token and token not in others:
            output.append(item)
    return output[:5]


def _normalize(text: str) -> str:
    lowered = text.lower()
    cleaned = []
    for char in lowered:
        if char.isalnum() or char.isspace():
            cleaned.append(char)
    return " ".join("".join(cleaned).split())
