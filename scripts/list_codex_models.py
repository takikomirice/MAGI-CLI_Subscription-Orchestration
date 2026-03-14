from __future__ import annotations

import sys


# Codex CLI does not currently expose a public "list models" command.
# Keep this curated fallback small and aligned with the local default config.
CURATED_MODELS = [
    "gpt-5.4",
    "gpt-5.3-codex",
    "gpt-5.2-codex",
    "gpt-5.2",
    "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini",
]


def main() -> int:
    for model in CURATED_MODELS:
        print(model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
