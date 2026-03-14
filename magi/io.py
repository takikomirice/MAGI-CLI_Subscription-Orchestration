from __future__ import annotations

from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    safe_content = content.encode("utf-8", errors="replace").decode("utf-8")
    path.write_text(safe_content, encoding="utf-8", errors="replace")


def write_yaml(path: Path, data: Any) -> None:
    write_text(path, dump_yaml(data))


def dump_yaml(value: Any, indent: int = 0) -> str:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            safe_key = str(key)
            if _is_scalar(item):
                lines.append(f"{prefix}{safe_key}: {_format_scalar(item)}")
            else:
                lines.append(f"{prefix}{safe_key}:")
                lines.append(dump_yaml(item, indent + 2))
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return f"{prefix}[]"
        lines = []
        for item in value:
            if _is_scalar(item):
                lines.append(f"{prefix}- {_format_scalar(item)}")
            else:
                lines.append(f"{prefix}-")
                lines.append(dump_yaml(item, indent + 2))
        return "\n".join(lines)
    return f"{prefix}{_format_scalar(value)}"


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).encode("utf-8", errors="replace").decode("utf-8")
    if text == "":
        return '""'
    if "\n" in text:
        indented = "\n".join(f"  {line}" for line in text.splitlines())
        return f"|\n{indented}"
    if any(ch in text for ch in [":", "#", "{", "}", "[", "]"]) or text.strip() != text:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text
