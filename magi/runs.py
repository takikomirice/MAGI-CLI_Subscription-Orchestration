from __future__ import annotations

import re
import shutil
from pathlib import Path

from magi.models import HandoffContext


def list_run_dirs(runs_dir: Path) -> list[Path]:
    if not runs_dir.exists():
        return []
    return sorted(path for path in runs_dir.iterdir() if path.is_dir())


def clean_runs(runs_dir: Path, keep: int | None = None, remove_all: bool = False) -> tuple[int, list[Path]]:
    run_dirs = list_run_dirs(runs_dir)
    if remove_all:
        targets = run_dirs
    else:
        keep = max(keep or 20, 0)
        targets = run_dirs[:-keep] if keep < len(run_dirs) else []

    for path in targets:
        shutil.rmtree(path, ignore_errors=False)
    return len(targets), targets


def resolve_handoff_context(runs_dir: Path, selector: str) -> HandoffContext:
    normalized = selector.strip()
    if not normalized:
        raise ValueError("Handoff selector cannot be empty.")

    run_dir = _resolve_run_dir(runs_dir, normalized)
    request_path = run_dir / "request.yaml"
    report_path = run_dir / "report.md"
    if not request_path.exists():
        raise ValueError(f"Handoff run is missing request metadata: {request_path}")
    if not report_path.exists():
        raise ValueError(f"Handoff run is missing report.md: {report_path}")

    mode = _read_request_field(request_path, "mode") or "ask"
    run_id = _read_request_field(request_path, "run_id") or run_dir.name
    report_markdown = report_path.read_text(encoding="utf-8", errors="replace").strip()
    if not report_markdown:
        raise ValueError(f"Handoff run report is empty: {report_path}")

    return HandoffContext(
        selector=normalized,
        run_id=run_id,
        mode=mode,
        run_dir=run_dir,
        report_path=report_path,
        report_markdown=report_markdown,
    )


def _resolve_run_dir(runs_dir: Path, selector: str) -> Path:
    run_dirs = list_run_dirs(runs_dir)
    if not run_dirs:
        raise ValueError(f"No runs found under {runs_dir}")

    if selector == "last":
        return run_dirs[-1]
    if selector == "last-plan":
        for run_dir in reversed(run_dirs):
            if _read_request_field(run_dir / "request.yaml", "mode") == "plan":
                return run_dir
        raise ValueError(f"No plan runs found under {runs_dir}")

    candidate = runs_dir / selector
    if candidate.exists() and candidate.is_dir():
        return candidate

    path_candidate = Path(selector).expanduser()
    if path_candidate.exists() and path_candidate.is_dir():
        return path_candidate.resolve()

    raise ValueError(
        "Unknown handoff selector. Use 'last', 'last-plan', a run ID, or a run directory path."
    )


def _read_request_field(request_path: Path, key: str) -> str:
    if not request_path.exists():
        return ""
    try:
        content = request_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    pattern = re.compile(rf"^{re.escape(key)}:\s*(.+)$", flags=re.MULTILINE)
    match = pattern.search(content)
    if not match:
        return ""
    return _parse_yaml_scalar(match.group(1).strip())


def _parse_yaml_scalar(value: str) -> str:
    if value in {'""', "null"}:
        return ""
    if len(value) >= 2 and value[0] == value[-1] == '"':
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return value
