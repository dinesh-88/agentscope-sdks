from __future__ import annotations

import builtins
import sys
from collections.abc import Callable
from typing import Any

from .anthropic import get_instrumentors as get_anthropic_instrumentors
from .anthropic import is_available as anthropic_available
from .base import BaseInstrumentor
from .openai import get_instrumentors as get_openai_instrumentors
from .openai import is_available as openai_available

_ORIGINAL_IMPORT = builtins.__import__
_IMPORT_HOOK_INSTALLED = False

_PROVIDER_LOADERS: dict[str, tuple[Callable[[], bool], Callable[[], list[BaseInstrumentor]]]] = {
    "openai": (openai_available, get_openai_instrumentors),
    "anthropic": (anthropic_available, get_anthropic_instrumentors),
}
_ACTIVE_INSTRUMENTORS: dict[str, BaseInstrumentor] = {}


def _normalize_providers(providers: list[str] | None) -> set[str]:
    if providers is None:
        return set(_PROVIDER_LOADERS.keys())
    return {provider.lower() for provider in providers}


def _register_instrumentors(providers: list[str] | None) -> None:
    selected = _normalize_providers(providers)
    for provider in selected:
        loader = _PROVIDER_LOADERS.get(provider)
        if loader is None:
            continue

        is_installed, build_instrumentors = loader
        if not is_installed():
            continue

        for instrumentor in build_instrumentors():
            _ACTIVE_INSTRUMENTORS.setdefault(instrumentor.target.key, instrumentor)


def _try_patch_available_targets() -> None:
    for instrumentor in _ACTIVE_INSTRUMENTORS.values():
        module = sys.modules.get(instrumentor.target.module)
        if module is None:
            continue
        instrumentor.patch(module)


def _install_import_hook() -> None:
    global _IMPORT_HOOK_INSTALLED
    if _IMPORT_HOOK_INSTALLED:
        return

    def _instrumenting_import(
        name: str,
        globals_dict: dict[str, Any] | None = None,
        locals_dict: dict[str, Any] | None = None,
        fromlist: tuple[Any, ...] = (),
        level: int = 0,
    ) -> Any:
        module = _ORIGINAL_IMPORT(name, globals_dict, locals_dict, fromlist, level)
        _try_patch_available_targets()
        return module

    builtins.__import__ = _instrumenting_import
    _IMPORT_HOOK_INSTALLED = True


def auto_trace(providers: list[str] | None = None) -> None:
    _register_instrumentors(providers)
    _install_import_hook()
    _try_patch_available_targets()


def auto_instrument(providers: list[str] | None = None) -> None:
    auto_trace(providers=providers)
