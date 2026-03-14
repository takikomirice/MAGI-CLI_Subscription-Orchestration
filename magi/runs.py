from __future__ import annotations

import shutil
from pathlib import Path


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
