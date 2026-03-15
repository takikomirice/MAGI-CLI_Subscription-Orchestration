from __future__ import annotations

import argparse
from pathlib import Path
import sys
import threading
import time

from magi.cancellation import RunCancellation, remove_history_file
from magi.config import AppConfig, load_config
from magi.model_catalog import (
    auto_refresh_model_catalogs,
    describe_model_catalogs,
    refresh_model_catalogs,
)
from magi.model_menu import open_model_menu
from magi.pipeline import run_request
from magi.runs import clean_runs, list_run_dirs

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import NestedCompleter
    from prompt_toolkit.history import FileHistory
except ImportError:
    PromptSession = None
    AutoSuggestFromHistory = None
    NestedCompleter = None
    FileHistory = None

try:
    import msvcrt
except ImportError:
    msvcrt = None


MODES = ("ask", "plan", "debug", "agent")
SHELL_COMMANDS = {
    "ask",
    "plan",
    "debug",
    "agent",
    "model",
    "mode",
    "models",
    "status",
    "runs",
    "last",
    "clean",
    "help",
    "exit",
    "quit",
}


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _interactive_shell(Path.cwd())

    if argv[0] == "runs":
        return _list_runs(Path.cwd())
    if argv[0] == "last":
        return _show_last(Path.cwd())
    if argv[0] == "clean":
        return _clean_command(Path.cwd(), argv[1:])
    if argv[0] == "models":
        return _models_command(Path.cwd(), argv[1:])

    parser = argparse.ArgumentParser(prog="magi", add_help=True)
    parser.add_argument("prompt", nargs="+", help="Natural-language request for the advisors.")
    parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
        help="Project root containing optional .magi.toml.",
    )
    parser.add_argument(
        "--providers",
        default="",
        help="Comma-separated provider names to run.",
    )
    parser.add_argument(
        "--models",
        default="",
        help="Comma-separated provider=model overrides.",
    )
    parser.add_argument(
        "--synth-provider",
        default="",
        help="Provider to use as the final synthesizer.",
    )
    parser.add_argument(
        "--efforts",
        default="",
        help="Comma-separated provider=effort overrides.",
    )
    parser.add_argument(
        "--mode",
        choices=MODES,
        default="ask",
        help="Execution mode for a one-shot request.",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    config = _load_runtime_config(project_root)
    selected = {item.strip() for item in args.providers.split(",") if item.strip()} or None
    synth_provider = args.synth_provider.strip() or None
    model_overrides = _parse_assignment_overrides(args.models)
    effort_overrides = _parse_assignment_overrides(args.efforts)
    prompt = " ".join(args.prompt).strip()
    cancellation = RunCancellation()
    stop_monitor = _start_escape_cancel_monitor(cancellation)
    try:
        artifacts = run_request(
            config,
            prompt,
            mode=args.mode,
            selected_providers=selected,
            synth_provider=synth_provider,
            model_overrides=model_overrides,
            effort_overrides=effort_overrides,
            progress=print,
            cancellation=cancellation,
        )
    finally:
        stop_monitor()
    print(f"[done] report: {artifacts.report_path}")
    _print_report(artifacts.report_path)
    return 0


def _configure_stdio() -> None:
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _interactive_shell(project_root: Path) -> int:
    config = _load_runtime_config(project_root)
    mode = "ask"
    selected_providers: set[str] | None = None
    synth_provider: str | None = None
    model_overrides: dict[str, str] = {}
    effort_overrides: dict[str, str] = {}
    model_catalog_menu_refreshed = False
    session = _build_prompt_session(config.project_root)
    _print_status(mode, config, selected_providers, synth_provider, model_overrides, effort_overrides)
    if PromptSession is None:
        print("history | prompt_toolkit not installed; using basic input() fallback")
    elif session is None:
        print("history | prompt_toolkit unavailable in this non-console context; using basic input() fallback")

    while True:
        try:
            line = _read_line(session, mode).strip()
        except EOFError:
            print("bye")
            return 0
        except KeyboardInterrupt:
            print()
            continue

        if not line:
            continue

        if line.startswith("/"):
            (
                should_exit,
                mode,
                selected_providers,
                synth_provider,
                model_overrides,
                effort_overrides,
                model_catalog_menu_refreshed,
            ) = _handle_slash_command(
                line,
                mode,
                config,
                selected_providers,
                synth_provider,
                model_overrides,
                effort_overrides,
                model_catalog_menu_refreshed,
            )
            if should_exit:
                return 0
            continue

        _run_and_report(config, line, mode, selected_providers, synth_provider, model_overrides, effort_overrides)


def _build_prompt_session(project_root: Path):
    if PromptSession is None or FileHistory is None or AutoSuggestFromHistory is None:
        return None
    history_path = project_root / ".magi_history"
    try:
        return PromptSession(
            history=FileHistory(str(history_path)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=_build_slash_completer(),
            complete_while_typing=True,
        )
    except Exception:
        return None


def _read_line(session, mode: str) -> str:
    prompt_text = f"MAGI [{mode}]> "
    if session is None:
        return input(prompt_text)
    return session.prompt(prompt_text)


def _handle_slash_command(
    line: str,
    mode: str,
    config: AppConfig,
    selected_providers: set[str] | None,
    synth_provider: str | None,
    model_overrides: dict[str, str],
    effort_overrides: dict[str, str],
    model_catalog_menu_refreshed: bool,
) -> tuple[bool, str, set[str] | None, str | None, dict[str, str], dict[str, str], bool]:
    command_text = line[1:].strip()
    if not command_text:
        print("Empty slash command. Try /help.")
        return False, mode, selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed

    if " " in command_text:
        command, payload = command_text.split(" ", 1)
        payload = payload.strip()
    else:
        command, payload = command_text, ""

    if command not in SHELL_COMMANDS:
        print(f"Unknown slash command: /{command}")
        return False, mode, selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed

    if command in MODES:
        mode = command
        print(f"mode: {mode}")
        _print_status(mode, config, selected_providers, synth_provider, model_overrides, effort_overrides)
        if payload:
            _run_and_report(config, payload, mode, selected_providers, synth_provider, model_overrides, effort_overrides)
        return False, mode, selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed

    if command == "model":
        selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed = _handle_model_command(
            payload,
            config,
            selected_providers,
            synth_provider,
            model_overrides,
            effort_overrides,
            model_catalog_menu_refreshed,
        )
        _print_status(mode, config, selected_providers, synth_provider, model_overrides, effort_overrides)
        return False, mode, selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed
    if command == "models":
        _handle_models_command(payload, config)
        return False, mode, selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed

    if command == "clean":
        _clean_runs_for_config(config, payload)
        return False, mode, selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed
    if command == "mode":
        print(f"mode: {mode}")
        return False, mode, selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed
    if command == "status":
        _print_status(mode, config, selected_providers, synth_provider, model_overrides, effort_overrides)
        return False, mode, selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed
    if command == "runs":
        _list_runs(config.project_root)
        return False, mode, selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed
    if command == "last":
        _show_last(config.project_root)
        return False, mode, selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed
    if command == "help":
        _print_shell_help()
        return False, mode, selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed
    if command in {"exit", "quit"}:
        print("bye")
        return True, mode, selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed

    return False, mode, selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed


def _run_and_report(
    config: AppConfig,
    prompt: str,
    mode: str,
    selected_providers: set[str] | None,
    synth_provider: str | None,
    model_overrides: dict[str, str],
    effort_overrides: dict[str, str],
) -> None:
    if selected_providers is not None and not selected_providers:
        print("No active providers. Open /model and enable at least one provider.")
        return
    cancellation = RunCancellation()
    stop_monitor = _start_escape_cancel_monitor(cancellation)
    try:
        artifacts = run_request(
            config,
            prompt,
            mode=mode,
            selected_providers=selected_providers,
            synth_provider=synth_provider,
            model_overrides=model_overrides,
            effort_overrides=effort_overrides,
            progress=print,
            cancellation=cancellation,
        )
    finally:
        stop_monitor()
    print(f"[done] report: {artifacts.report_path}")
    _print_report(artifacts.report_path)


def _list_runs(project_root: Path) -> int:
    config = load_config(project_root)
    run_dirs = list_run_dirs(config.runs_dir)
    if not run_dirs:
        print("No runs found.")
        return 0
    for path in run_dirs:
        print(path)
    return 0


def _show_last(project_root: Path) -> int:
    config = load_config(project_root)
    run_dirs = list_run_dirs(config.runs_dir)
    if not run_dirs:
        print("No runs found.")
        return 1
    latest = run_dirs[-1] / "report.md"
    print(latest)
    return 0


def _clean_command(project_root: Path, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="magi clean", add_help=True)
    parser.add_argument("target", nargs="?", default="20", help="Keep count or 'all'.")
    parser.add_argument("--history", action="store_true", help="Also remove the .magi_history file.")
    parser.add_argument("--project-root", default=str(project_root), help="Project root containing optional .magi.toml.")
    args = parser.parse_args(argv)
    config = load_config(Path(args.project_root).resolve())
    _clean_runs_for_config(config, args.target, remove_history=args.history)
    return 0


def _models_command(project_root: Path, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="magi models", add_help=True)
    parser.add_argument("action", nargs="?", default="show", choices=("show", "refresh"))
    parser.add_argument("provider", nargs="?", default="all", help="Provider name or 'all'.")
    parser.add_argument("--project-root", default=str(project_root), help="Project root containing optional .magi.toml.")
    args = parser.parse_args(argv)
    config = _load_runtime_config(Path(args.project_root).resolve())
    if args.action == "refresh":
        target = None if args.provider == "all" else {args.provider}
        refresh_model_catalogs(config, target_providers=target, force=True, progress=print)
    print(describe_model_catalogs(config))
    return 0


def _clean_runs_for_config(config: AppConfig, target: str, remove_history: bool = False) -> None:
    parsed_target, parsed_remove_history = _parse_clean_target(target)
    remove_history = remove_history or parsed_remove_history

    if parsed_target == "all":
        removed_count, _removed = clean_runs(config.runs_dir, remove_all=True)
        history_suffix = _clean_history_suffix(config, remove_history)
        print(f"cleaned {removed_count} run(s) from {config.runs_dir}{history_suffix}")
        return
    try:
        keep = int(parsed_target or "20")
    except ValueError:
        print("Usage: /clean [all|N] [--history]")
        return
    removed_count, _removed = clean_runs(config.runs_dir, keep=keep)
    history_suffix = _clean_history_suffix(config, remove_history)
    print(f"cleaned {removed_count} run(s); kept latest {keep}{history_suffix}")


def _parse_clean_target(target: str) -> tuple[str, bool]:
    parts = [item.strip() for item in target.split() if item.strip()]
    remove_history = False
    filtered: list[str] = []
    for item in parts:
        if item in {"history", "--history"}:
            remove_history = True
            continue
        filtered.append(item)
    return (filtered[0] if filtered else "20"), remove_history


def _clean_history_suffix(config: AppConfig, remove_history: bool) -> str:
    if not remove_history:
        return ""
    removed = remove_history_file(config.project_root)
    return " and removed .magi_history" if removed else " and left .magi_history unchanged"


def _start_escape_cancel_monitor(cancellation: RunCancellation):
    if msvcrt is None or not sys.stdin or not sys.stdin.isatty():
        return lambda: None

    stop_event = threading.Event()

    def _monitor() -> None:
        while not stop_event.is_set() and not cancellation.is_cancelled():
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key == "\x1b" and cancellation.cancel():
                    print("[cancel] escape pressed; stopping active providers...")
                    return
            time.sleep(0.05)

    thread = threading.Thread(target=_monitor, name="magi-esc-cancel", daemon=True)
    thread.start()

    def _stop() -> None:
        stop_event.set()
        thread.join(timeout=0.2)

    return _stop


def _print_help() -> None:
    print("Usage:")
    print('  magi "your request"')
    print('  magi --mode plan "your request"')
    print('  magi --providers codex --models codex=gpt-5.4 --efforts codex=high "your request"')
    print('  magi --synth-provider gemini "your request"')
    print("  magi runs")
    print("  magi last")
    print("  magi models [show|refresh] [provider|all]")
    print("  magi clean [20|all] [--history]")
    print("  magi")


def _print_shell_help() -> None:
    print("Slash commands:")
    print("  /ask [prompt]    switch to ask mode")
    print("  /plan [prompt]   switch to plan mode")
    print("  /debug [prompt]  switch to debug mode")
    print("  /agent [prompt]  switch to agent mode")
    print("  /model           open the provider/model/effort menu")
    print("  /model show      print the current provider/model/effort state")
    print("  /models          show model catalog sources and values")
    print("  /models refresh [provider|all]  refresh model catalogs now")
    print("  /clean [N|all] [--history]   remove old runs; default keeps latest 20")
    print("  /mode            show current mode")
    print("  /status          show provider and quota placeholders")
    print("  /runs            list saved runs")
    print("  /last            print the latest report path")
    print("  /help            show help")
    print("  /exit            quit MAGI")


def _print_status(
    mode: str,
    config: AppConfig,
    selected_providers: set[str] | None,
    synth_provider: str | None,
    model_overrides: dict[str, str],
    effort_overrides: dict[str, str],
) -> None:
    enabled = [provider for provider in config.providers if provider.enabled]
    active = selected_providers or {provider.name for provider in enabled}
    quota = " | ".join(f"{provider.name}: --%" for provider in enabled) or "none"
    detail_parts = []
    for provider in enabled:
        if provider.name not in active:
            continue
        resolved_model = model_overrides.get(provider.name) or provider.default_model or "default"
        resolved_effort = effort_overrides.get(provider.name) or provider.default_effort or "default"
        role = "synth" if provider.name == synth_provider else "advisor"
        detail_parts.append(f"{provider.name}={resolved_model}/{resolved_effort}/{role}")
    detail_text = ", ".join(detail_parts) or "none"
    active_text = ", ".join(sorted(active)) if active else "none"
    print(f"status | mode: {mode} | active: {active_text} | models: {detail_text} | quota {quota}")


def _handle_model_command(
    payload: str,
    config: AppConfig,
    selected_providers: set[str] | None,
    synth_provider: str | None,
    model_overrides: dict[str, str],
    effort_overrides: dict[str, str],
    model_catalog_menu_refreshed: bool,
) -> tuple[set[str] | None, str | None, dict[str, str], dict[str, str], bool]:
    enabled_names = {provider.name for provider in config.providers if provider.enabled}
    if not payload:
        if not model_catalog_menu_refreshed:
            print("refreshing model catalogs before opening /model ...")
            refresh_model_catalogs(config, force=True, progress=print)
            model_catalog_menu_refreshed = True
        result = open_model_menu(config, selected_providers, model_overrides, effort_overrides, synth_provider)
        return result.selected_providers, result.synth_provider, result.model_overrides, result.effort_overrides, model_catalog_menu_refreshed
    if payload == "show":
        print(_describe_models(config, selected_providers, synth_provider, model_overrides, effort_overrides))
        return selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed
    if payload == "all":
        print("active providers: all")
        return None, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed
    if payload == "reset":
        print("model, effort, and synthesizer state cleared; active providers: all")
        return None, None, {}, {}, model_catalog_menu_refreshed

    parts = payload.split()
    target = parts[0].strip()
    model = parts[1].strip() if len(parts) > 1 else ""
    effort = parts[2].strip() if len(parts) > 2 else ""
    if target not in enabled_names:
        print(f"Unknown provider: {target}")
        return selected_providers, synth_provider, model_overrides, effort_overrides, model_catalog_menu_refreshed

    next_selected = {target}
    next_synth = synth_provider if synth_provider == target else None
    next_models = dict(model_overrides)
    next_efforts = dict(effort_overrides)
    if model:
        next_models[target] = model
    if effort:
        next_efforts[target] = effort
    detail = []
    if model:
        detail.append(f"model: {model}")
    if effort:
        detail.append(f"effort: {effort}")
    suffix = " | " + " | ".join(detail) if detail else ""
    print(f"active provider: {target}{suffix}")
    return next_selected, next_synth, next_models, next_efforts, model_catalog_menu_refreshed


def _describe_models(
    config: AppConfig,
    selected_providers: set[str] | None,
    synth_provider: str | None,
    model_overrides: dict[str, str],
    effort_overrides: dict[str, str],
) -> str:
    enabled = [provider for provider in config.providers if provider.enabled]
    active = selected_providers or {provider.name for provider in enabled}
    lines = ["model state:"]
    for provider in enabled:
        state = "active" if provider.name in active else "inactive"
        role = "synth" if provider.name == synth_provider else "advisor"
        model = model_overrides.get(provider.name) or provider.default_model or "default"
        effort = effort_overrides.get(provider.name) or provider.default_effort or "default"
        lines.append(f"  {provider.name}: {state}, role={role}, model={model}, effort={effort}")
    return "\n".join(lines)


def _parse_assignment_overrides(raw: str) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for item in raw.split(","):
        entry = item.strip()
        if not entry or "=" not in entry:
            continue
        provider, value = entry.split("=", 1)
        provider = provider.strip()
        value = value.strip()
        if provider and value:
            overrides[provider] = value
    return overrides


def _print_report(report_path: Path) -> None:
    try:
        content = report_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        print(f"[warn] failed to read report: {exc}")
        return
    if not content:
        print("[warn] report is empty")
        return
    print()
    print(content)
    print()


def _handle_models_command(payload: str, config: AppConfig) -> None:
    parts = payload.split()
    action = parts[0] if parts else "show"
    target_name = parts[1] if len(parts) > 1 else "all"
    if action not in {"show", "refresh"}:
        print("Usage: /models [show|refresh] [provider|all]")
        return
    target = None if target_name == "all" else {target_name}
    if action == "refresh":
        refresh_model_catalogs(config, target_providers=target, force=True, progress=print)
    print(describe_model_catalogs(config))


def _load_runtime_config(project_root: Path) -> AppConfig:
    config = load_config(project_root)
    auto_refresh_model_catalogs(config)
    return config


def _build_slash_completer():
    if NestedCompleter is None:
        return None
    return NestedCompleter.from_nested_dict(
        {
            "/ask": None,
            "/plan": None,
            "/debug": None,
            "/agent": None,
            "/model": {
                "show": None,
                "all": None,
                "reset": None,
                "codex": None,
                "claude": None,
                "gemini": None,
            },
            "/models": {
                "show": None,
                "refresh": {
                    "all": None,
                    "codex": None,
                    "claude": None,
                    "gemini": None,
                },
            },
            "/mode": None,
            "/status": None,
            "/runs": None,
            "/last": None,
            "/clean": {
                "all": None,
                "20": None,
            },
            "/help": None,
            "/exit": None,
            "/quit": None,
        }
    )
