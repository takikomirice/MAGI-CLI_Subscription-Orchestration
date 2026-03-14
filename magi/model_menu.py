from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from magi.config import AppConfig, ProviderConfig


if sys.platform == "win32":
    import msvcrt
else:
    msvcrt = None


@dataclass(slots=True)
class MenuState:
    level: int = 0
    provider_index: int = 0
    model_index: int = 0
    effort_index: int = 0


@dataclass(slots=True)
class MenuResult:
    selected_providers: set[str] | None
    model_overrides: dict[str, str]
    effort_overrides: dict[str, str]
    synth_provider: str | None


def open_model_menu(
    config: AppConfig,
    selected_providers: set[str] | None,
    model_overrides: dict[str, str],
    effort_overrides: dict[str, str],
    synth_provider: str | None,
) -> MenuResult:
    if msvcrt is None:
        raise RuntimeError("Interactive model menu is only supported on Windows terminals.")

    enabled = [provider for provider in config.providers if provider.enabled]
    active = set(selected_providers) if selected_providers is not None else {provider.name for provider in enabled}
    synth = synth_provider if synth_provider in active else None
    models = dict(model_overrides)
    efforts = dict(effort_overrides)
    state = MenuState()
    message = ""

    if not enabled:
        return MenuResult(selected_providers, models, efforts, synth_provider)

    while True:
        _render(enabled, active, synth, models, efforts, state, message)
        key = _read_key()
        if key == "UP":
            _move(enabled, state, -1)
            message = ""
            continue
        if key == "DOWN":
            _move(enabled, state, 1)
            message = ""
            continue
        if key == "SPACE" and state.level == 0:
            provider = enabled[state.provider_index]
            if provider.name not in active:
                active.add(provider.name)
                message = f"{provider.name}: advisor"
                continue
            if synth == provider.name:
                synth = None
                active.remove(provider.name)
                message = f"{provider.name}: off"
                continue
            if synth is not None and synth != provider.name:
                active.remove(provider.name)
                message = f"{provider.name}: off"
                continue
            synth = provider.name
            message = f"{provider.name}: synthesizer"
            continue
        if key == "ENTER":
            provider = enabled[state.provider_index]
            if state.level == 0:
                state.level = 1
                state.model_index = _current_model_index(provider, models)
                message = ""
                continue
            if state.level == 1:
                model = _model_options(provider)[state.model_index]
                models[provider.name] = model
                state.level = 2
                state.effort_index = _current_effort_index(provider, efforts)
                message = ""
                continue
            effort = _effort_options(provider)[state.effort_index]
            efforts[provider.name] = effort
            state.level = 0
            message = ""
            continue
        if key == "ESC":
            if state.level == 2:
                state.level = 1
                message = ""
                continue
            if state.level == 1:
                state.level = 0
                message = ""
                continue
            os.system("cls")
            normalized_active = set(active)
            selected = None if normalized_active == {provider.name for provider in enabled} else normalized_active
            return MenuResult(selected, models, efforts, synth)


def _render(
    enabled: list[ProviderConfig],
    active: set[str],
    synth: str | None,
    models: dict[str, str],
    efforts: dict[str, str],
    state: MenuState,
    message: str,
) -> None:
    os.system("cls")
    print("MAGI model menu")
    print("Enter: descend/select | Esc: back/exit | Space: cycle [× off] -> [• advisor] -> [○ synth]")
    print()

    if state.level == 0:
        print("Providers")
    elif state.level == 1:
        print(f"Providers > {enabled[state.provider_index].name} > Models")
    else:
        print(f"Providers > {enabled[state.provider_index].name} > Effort")
    print()

    for index, provider in enumerate(enabled):
        marker = ">" if state.level == 0 and index == state.provider_index else " "
        if provider.name == synth:
            role = "[○]"
        elif provider.name in active:
            role = "[•]"
        else:
            role = "[×]"
        model = models.get(provider.name) or provider.default_model or "default"
        effort = efforts.get(provider.name) or provider.default_effort or "default"
        print(f"{marker} {role} {provider.name:<8} model={model:<20} effort={effort}")

    if message:
        print()
        print(message)

    provider = enabled[state.provider_index]
    if state.level == 1:
        print()
        print("Models")
        for index, model in enumerate(_model_options(provider)):
            marker = ">" if index == state.model_index else " "
            current = "*" if (models.get(provider.name) or provider.default_model) == model else " "
            print(f"{marker} [{current}] {model}")
    elif state.level == 2:
        print()
        print("Effort")
        for index, effort in enumerate(_effort_options(provider)):
            marker = ">" if index == state.effort_index else " "
            current = "*" if (efforts.get(provider.name) or provider.default_effort) == effort else " "
            print(f"{marker} [{current}] {effort}")


def _move(enabled: list[ProviderConfig], state: MenuState, delta: int) -> None:
    provider = enabled[state.provider_index]
    if state.level == 0:
        state.provider_index = (state.provider_index + delta) % len(enabled)
        return
    if state.level == 1:
        options = _model_options(provider)
        state.model_index = (state.model_index + delta) % len(options)
        return
    options = _effort_options(provider)
    state.effort_index = (state.effort_index + delta) % len(options)


def _current_model_index(provider: ProviderConfig, models: dict[str, str]) -> int:
    current = models.get(provider.name) or provider.default_model or "default"
    options = _model_options(provider)
    if current in options:
        return options.index(current)
    return 0


def _current_effort_index(provider: ProviderConfig, efforts: dict[str, str]) -> int:
    current = efforts.get(provider.name) or provider.default_effort or "default"
    options = _effort_options(provider)
    if current in options:
        return options.index(current)
    return 0


def _model_options(provider: ProviderConfig) -> list[str]:
    options = list(provider.model_options)
    if provider.default_model and provider.default_model not in options:
        options.insert(0, provider.default_model)
    return options or [provider.default_model or "default"]


def _effort_options(provider: ProviderConfig) -> list[str]:
    options = list(provider.effort_options)
    if provider.default_effort and provider.default_effort not in options:
        options.insert(0, provider.default_effort)
    return options or [provider.default_effort or "default"]


def _read_key() -> str:
    key = msvcrt.getwch()
    if key in {"\r", "\n"}:
        return "ENTER"
    if key == "\x1b":
        return "ESC"
    if key == " ":
        return "SPACE"
    if key in {"\x00", "\xe0"}:
        special = msvcrt.getwch()
        if special == "H":
            return "UP"
        if special == "P":
            return "DOWN"
    return "OTHER"
