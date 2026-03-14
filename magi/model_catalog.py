from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable

from magi.config import AppConfig, ProviderConfig
from magi.io import ensure_dir


ProgressCallback = Callable[[str], None]
CACHE_DIRNAME = ".magi-cache"
CACHE_FILENAME = "model_catalogs.json"


@dataclass(slots=True)
class ModelCatalogRefreshResult:
    provider: str
    ok: bool
    refreshed: bool
    models: list[str]
    message: str = ""


def refresh_model_catalogs(
    config: AppConfig,
    target_providers: set[str] | None = None,
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> list[ModelCatalogRefreshResult]:
    cache = load_model_catalog_cache(config.project_root)
    results: list[ModelCatalogRefreshResult] = []
    changed = False

    for provider in config.providers:
        if target_providers and provider.name not in target_providers:
            continue
        result = _refresh_provider_catalog(provider, cache.get(provider.name), force)
        results.append(result)
        if result.refreshed and result.ok:
            cache[provider.name] = {
                "models": result.models,
                "updated_at": _utc_now_iso(),
            }
            changed = True
        _emit(progress, _format_refresh_result(result))

    if changed:
        write_model_catalog_cache(config.project_root, cache)
    apply_model_catalog_cache(config, cache)
    return results


def auto_refresh_model_catalogs(
    config: AppConfig,
    progress: ProgressCallback | None = None,
) -> list[ModelCatalogRefreshResult]:
    return refresh_model_catalogs(config, force=False, progress=progress)


def apply_model_catalog_cache(config: AppConfig, cache: dict[str, dict[str, object]] | None = None) -> None:
    cache = cache if cache is not None else load_model_catalog_cache(config.project_root)
    for provider in config.providers:
        entry = cache.get(provider.name) or {}
        models = [str(item) for item in entry.get("models", []) if str(item).strip()]
        if not models:
            continue
        provider.model_options = _merge_models(provider.default_model, models)


def describe_model_catalogs(config: AppConfig) -> str:
    cache = load_model_catalog_cache(config.project_root)
    lines = ["model catalogs:"]
    for provider in config.providers:
        entry = cache.get(provider.name) or {}
        updated_at = str(entry.get("updated_at") or "never")
        source = "cached" if entry.get("models") else "static"
        models = provider.model_options or ([provider.default_model] if provider.default_model else [])
        joined = ", ".join(models) if models else "none"
        lines.append(f"  {provider.name}: source={source}, updated_at={updated_at}, models={joined}")
    return "\n".join(lines)


def load_model_catalog_cache(project_root: Path) -> dict[str, dict[str, object]]:
    cache_path = _cache_path(project_root)
    if not cache_path.exists():
        return {}
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    providers = raw.get("providers")
    if not isinstance(providers, dict):
        return {}
    normalized: dict[str, dict[str, object]] = {}
    for name, entry in providers.items():
        if not isinstance(entry, dict):
            continue
        normalized[str(name)] = entry
    return normalized


def write_model_catalog_cache(project_root: Path, cache: dict[str, dict[str, object]]) -> None:
    cache_path = _cache_path(project_root)
    ensure_dir(cache_path.parent)
    payload = {
        "updated_at": _utc_now_iso(),
        "providers": cache,
    }
    cache_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _cache_path(project_root: Path) -> Path:
    return project_root / CACHE_DIRNAME / CACHE_FILENAME


def _refresh_provider_catalog(
    provider: ProviderConfig,
    cache_entry: dict[str, object] | None,
    force: bool,
) -> ModelCatalogRefreshResult:
    if provider.type != "cli":
        return ModelCatalogRefreshResult(
            provider=provider.name,
            ok=True,
            refreshed=False,
            models=list(provider.model_options),
            message="mock provider; using static models",
        )

    if not provider.model_discovery_command:
        return ModelCatalogRefreshResult(
            provider=provider.name,
            ok=True,
            refreshed=False,
            models=list(provider.model_options),
            message="no discovery command configured; using static models",
        )

    if not force and not _is_stale(cache_entry, provider.model_discovery_ttl_hours):
        models = [str(item) for item in (cache_entry or {}).get("models", []) if str(item).strip()]
        return ModelCatalogRefreshResult(
            provider=provider.name,
            ok=True,
            refreshed=False,
            models=_merge_models(provider.default_model, models) if models else list(provider.model_options),
            message="cache is fresh",
        )

    command = [part.format(provider=provider.name) for part in provider.model_discovery_command]
    resolved_executable = shutil.which(command[0]) if command else None
    if not command or resolved_executable is None:
        return ModelCatalogRefreshResult(
            provider=provider.name,
            ok=False,
            refreshed=False,
            models=list(provider.model_options),
            message=f"executable not found on PATH: {command[0] if command else ''}",
        )
    command[0] = resolved_executable
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=provider.model_discovery_timeout_seconds,
            check=False,
        )
    except OSError as exc:
        return ModelCatalogRefreshResult(
            provider=provider.name,
            ok=False,
            refreshed=False,
            models=list(provider.model_options),
            message=str(exc),
        )
    except subprocess.TimeoutExpired:
        return ModelCatalogRefreshResult(
            provider=provider.name,
            ok=False,
            refreshed=False,
            models=list(provider.model_options),
            message=f"timed out after {provider.model_discovery_timeout_seconds} seconds",
        )

    if completed.returncode != 0:
        return ModelCatalogRefreshResult(
            provider=provider.name,
            ok=False,
            refreshed=False,
            models=list(provider.model_options),
            message=(completed.stderr or completed.stdout or f"exit code {completed.returncode}").strip(),
        )

    discovered = _parse_discovered_models(completed.stdout or "", provider.model_discovery_regex)
    if not discovered:
        return ModelCatalogRefreshResult(
            provider=provider.name,
            ok=False,
            refreshed=False,
            models=list(provider.model_options),
            message="discovery command returned no model names",
        )

    return ModelCatalogRefreshResult(
        provider=provider.name,
        ok=True,
        refreshed=True,
        models=_merge_models(provider.default_model, discovered),
        message=f"discovered {len(discovered)} model(s)",
    )


def _parse_discovered_models(stdout: str, pattern: str) -> list[str]:
    regex = re.compile(pattern) if pattern else None
    models: list[str] = []
    seen: set[str] = set()
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if regex is None:
            candidate = line
        else:
            match = regex.search(line)
            if match is None:
                continue
            candidate = match.group(1) if match.groups() else match.group(0)
        model = candidate.strip()
        if not model or model in seen:
            continue
        seen.add(model)
        models.append(model)
    return models


def _merge_models(default_model: str, models: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in [default_model, *models]:
        model = str(item).strip()
        if not model or model in seen:
            continue
        seen.add(model)
        merged.append(model)
    return merged


def _is_stale(cache_entry: dict[str, object] | None, ttl_hours: int) -> bool:
    if cache_entry is None:
        return True
    if ttl_hours <= 0:
        return True
    updated_at = str(cache_entry.get("updated_at") or "").strip()
    if not updated_at:
        return True
    try:
        parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return age >= timedelta(hours=ttl_hours)


def _format_refresh_result(result: ModelCatalogRefreshResult) -> str:
    status = "ok" if result.ok else "error"
    action = "refreshed" if result.refreshed else "kept"
    suffix = f" | {result.message}" if result.message else ""
    return f"[models] {result.provider}: {status}, {action}, {len(result.models)} model(s){suffix}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)
