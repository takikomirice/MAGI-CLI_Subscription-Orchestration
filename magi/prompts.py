from __future__ import annotations

from pathlib import Path
import json

from magi.models import HandoffContext


PROMPTS_DIR = Path(__file__).with_name("prompts")
MODE_TO_PROMPT = {
    "ask": "advisor.md",
    "plan": "plan.md",
    "debug": "debug.md",
    "agent": "agent.md",
}


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def build_mode_prompt(
    mode: str,
    user_request: str,
    project_name: str,
    project_root: Path,
    handoff: HandoffContext | None = None,
    project_plan_markdown: str = "",
    retry_feedback: str = "",
) -> str:
    prompt_name = MODE_TO_PROMPT.get(mode, "advisor.md")
    template = load_prompt(prompt_name)
    prompt = template.format(
        user_request=user_request.strip(),
        project_name=project_name,
        project_root=str(project_root),
        mode=mode,
    )
    prompt += _render_project_plan_block(project_plan_markdown)
    if handoff is None:
        return prompt + _render_retry_feedback(retry_feedback)
    return prompt + _render_handoff_block(handoff) + _render_retry_feedback(retry_feedback)


def build_synthesis_report_prompt(
    user_request: str,
    mode: str,
    project_name: str,
    project_root: Path,
    advisor_results: list[dict[str, object]],
    heuristic_synthesis: dict[str, object],
) -> str:
    template = load_prompt("synth_report.md")
    return template.format(
        user_request=user_request.strip(),
        project_name=project_name,
        project_root=str(project_root),
        mode=mode,
        advisor_results_json=json.dumps(advisor_results, ensure_ascii=False, indent=2),
        heuristic_synthesis_json=json.dumps(heuristic_synthesis, ensure_ascii=False, indent=2),
    )


def _render_handoff_block(handoff: HandoffContext) -> str:
    return (
        "\n\nPrevious MAGI handoff context:\n"
        f"- source_selector: {handoff.selector}\n"
        f"- source_run_id: {handoff.run_id}\n"
        f"- source_mode: {handoff.mode}\n"
        f"- source_report_path: {handoff.report_path}\n"
        "- Treat this prior MAGI report as input context.\n"
        "- Preserve its constraints and decisions unless the new user request explicitly changes them.\n\n"
        "<MAGI_HANDOFF_REPORT>\n"
        f"{handoff.report_markdown}\n"
        "</MAGI_HANDOFF_REPORT>\n"
    )


def _render_retry_feedback(retry_feedback: str) -> str:
    if not retry_feedback.strip():
        return ""
    return (
        "\n\nVerification feedback from the previous attempt:\n"
        "- Fix the failing checks before declaring the work complete.\n"
        "- Do not repeat the same unchanged implementation if the failures remain relevant.\n\n"
        "<MAGI_VERIFICATION_FEEDBACK>\n"
        f"{retry_feedback.strip()}\n"
        "</MAGI_VERIFICATION_FEEDBACK>\n"
    )


def _render_project_plan_block(project_plan_markdown: str) -> str:
    if not project_plan_markdown.strip():
        return ""
    return (
        "\n\nCurrent project plan:\n"
        "- Update this plan carefully instead of discarding it wholesale.\n"
        "- Preserve still-valid decisions and refine the parts that need to change.\n\n"
        "<MAGI_PROJECT_PLAN>\n"
        f"{project_plan_markdown.strip()}\n"
        "</MAGI_PROJECT_PLAN>\n"
    )
