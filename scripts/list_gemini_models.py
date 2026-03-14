from __future__ import annotations

import os
import re
import sys
from pathlib import Path


ORDERED_EXPORTS = [
    "PREVIEW_GEMINI_3_1_MODEL",
    "PREVIEW_GEMINI_FLASH_MODEL",
    "PREVIEW_GEMINI_MODEL",
    "DEFAULT_GEMINI_MODEL",
    "DEFAULT_GEMINI_FLASH_MODEL",
    "DEFAULT_GEMINI_FLASH_LITE_MODEL",
]

FALLBACK_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3-pro-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]


def main() -> int:
    models_file = _find_models_file()
    if models_file is None:
        _print_models(FALLBACK_MODELS)
        return 0

    exports = _parse_exported_models(models_file.read_text(encoding="utf-8", errors="replace"))
    discovered = [exports[name] for name in ORDERED_EXPORTS if name in exports]
    _print_models(discovered or FALLBACK_MODELS)
    return 0


def _find_models_file() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    candidate = (
        Path(appdata)
        / "npm"
        / "node_modules"
        / "@google"
        / "gemini-cli"
        / "node_modules"
        / "@google"
        / "gemini-cli-core"
        / "dist"
        / "src"
        / "config"
        / "models.js"
    )
    return candidate if candidate.exists() else None


def _parse_exported_models(text: str) -> dict[str, str]:
    pairs = re.findall(r"export const (\w+) = '([^']+)';", text)
    return {
        name: value
        for name, value in pairs
        if value.startswith("gemini-") and not value.endswith("-customtools")
    }


def _print_models(models: list[str]) -> None:
    seen: set[str] = set()
    for model in models:
        if not model or model in seen:
            continue
        seen.add(model)
        print(model)


if __name__ == "__main__":
    sys.exit(main())
