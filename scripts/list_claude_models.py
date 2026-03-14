from __future__ import annotations

import os
import re
import sys
from pathlib import Path


PRIORITY = [
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
    "claude-opus-4-5",
    "claude-opus-4-1",
]

FALLBACK_MODELS = [
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
    "claude-opus-4-5",
    "claude-opus-4-1",
]


def main() -> int:
    bundle = _find_bundle()
    if bundle is None:
        _print_models(FALLBACK_MODELS)
        return 0

    models = _extract_models(bundle.read_text(encoding="utf-8", errors="replace"))
    _print_models(models or FALLBACK_MODELS)
    return 0


def _find_bundle() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    candidate = (
        Path(appdata)
        / "npm"
        / "node_modules"
        / "@anthropic-ai"
        / "claude-code"
        / "cli.js"
    )
    return candidate if candidate.exists() else None


def _extract_models(text: str) -> list[str]:
    matches = set(re.findall(r"\bclaude-(?:opus|sonnet|haiku)-\d(?:-\d)?\b", text))
    filtered = [model for model in matches if _is_supported_family_alias(model)]
    ordered = [model for model in PRIORITY if model in filtered]
    extras = sorted(
        (model for model in filtered if model not in PRIORITY),
        key=_sort_key,
    )
    return ordered + extras


def _is_supported_family_alias(model: str) -> bool:
    parts = model.split("-")
    if len(parts) != 4:
        return False
    try:
        major = int(parts[2])
        minor = int(parts[3])
    except ValueError:
        return False
    return major >= 4 and minor > 0


def _sort_key(model: str) -> tuple[int, int, int]:
    _, family, major, *rest = model.split("-")
    minor = int(rest[0]) if rest else 0
    family_order = {"sonnet": 0, "opus": 1, "haiku": 2}.get(family, 9)
    return (-int(major), -minor, family_order)


def _print_models(models: list[str]) -> None:
    seen: set[str] = set()
    for model in models:
        if not model or model in seen:
            continue
        seen.add(model)
        print(model)


if __name__ == "__main__":
    sys.exit(main())
