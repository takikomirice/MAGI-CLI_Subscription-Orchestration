from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import tomllib


DEFAULT_EFFORT_OPTIONS = ["default", "low", "medium", "high", "xhigh"]


@dataclass(slots=True)
class ProviderConfig:
    name: str
    type: str = "mock"
    enabled: bool = True
    command: list[str] = field(default_factory=list)
    model_discovery_command: list[str] = field(default_factory=list)
    model_discovery_regex: str = ""
    model_discovery_ttl_hours: int = 24
    model_discovery_timeout_seconds: int = 15
    stdin_prompt: bool = False
    timeout_seconds: int = 180
    default_model: str = ""
    model_options: list[str] = field(default_factory=list)
    default_effort: str = "default"
    effort_options: list[str] = field(default_factory=lambda: list(DEFAULT_EFFORT_OPTIONS))


@dataclass(slots=True)
class AppConfig:
    project_root: Path
    project_name: str
    runs_dir: Path
    providers: list[ProviderConfig]


def load_config(project_root: Path) -> AppConfig:
    config_path = project_root / ".magi.toml"
    if not config_path.exists():
        return default_config(project_root)

    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    project_name = str(raw.get("project_name") or project_root.name)
    runs_dir = project_root / str(raw.get("runs_dir") or "runs")
    provider_table = raw.get("providers") or {}
    providers = []
    for name, values in provider_table.items():
        providers.append(_provider_from_table(name, values))

    if not providers:
        providers = default_config(project_root).providers

    return AppConfig(
        project_root=project_root,
        project_name=project_name,
        runs_dir=runs_dir,
        providers=providers,
    )


def default_config(project_root: Path) -> AppConfig:
    providers = [
        ProviderConfig(
            name="codex",
            type="mock",
            default_model="gpt-5.4",
            model_options=[
                "gpt-5.4",
                "gpt-5.3-codex",
                "gpt-5.2-codex",
                "gpt-5.2",
                "gpt-5.1-codex-max",
                "gpt-5.1-codex-mini",
            ],
        ),
        ProviderConfig(
            name="claude",
            type="mock",
            default_model="claude-sonnet-4-6",
            model_options=["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"],
        ),
        ProviderConfig(
            name="gemini",
            type="mock",
            default_model="gemini-3.1-pro-preview",
            model_options=[
                "gemini-3.1-pro-preview",
                "gemini-3-flash-preview",
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
            ],
        ),
    ]
    return AppConfig(
        project_root=project_root,
        project_name=project_root.name,
        runs_dir=project_root / "runs",
        providers=providers,
    )


def _provider_from_table(name: str, raw: dict[str, Any]) -> ProviderConfig:
    command = [str(item) for item in raw.get("command", [])]
    model_discovery_command = [str(item) for item in raw.get("model_discovery_command", [])]
    default_model = str(raw.get("default_model") or "")
    model_options = [str(item) for item in raw.get("model_options", [])]
    if default_model and default_model not in model_options:
        model_options.insert(0, default_model)
    effort_options = [str(item) for item in raw.get("effort_options", [])] or list(DEFAULT_EFFORT_OPTIONS)
    default_effort = str(raw.get("default_effort") or "default")
    if default_effort not in effort_options:
        effort_options.insert(0, default_effort)
    return ProviderConfig(
        name=name,
        type=str(raw.get("type") or "mock"),
        enabled=bool(raw.get("enabled", True)),
        command=command,
        model_discovery_command=model_discovery_command,
        model_discovery_regex=str(raw.get("model_discovery_regex") or ""),
        model_discovery_ttl_hours=int(raw.get("model_discovery_ttl_hours", 24)),
        model_discovery_timeout_seconds=int(raw.get("model_discovery_timeout_seconds", 15)),
        stdin_prompt=bool(raw.get("stdin_prompt", False)),
        timeout_seconds=int(raw.get("timeout_seconds", 180)),
        default_model=default_model,
        model_options=model_options,
        default_effort=default_effort,
        effort_options=effort_options,
    )
