from __future__ import annotations

from pathlib import Path
import json


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
) -> str:
    prompt_name = MODE_TO_PROMPT.get(mode, "advisor.md")
    template = load_prompt(prompt_name)
    return template.format(
        user_request=user_request.strip(),
        project_name=project_name,
        project_root=str(project_root),
        mode=mode,
    )


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
