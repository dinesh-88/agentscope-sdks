from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class TargetSpec:
    key: str
    provider: str
    module: str
    path: tuple[str, ...]
    request_extractor: Callable[[Callable[..., Any], tuple[Any, ...], dict[str, Any]], dict[str, Any]]
    response_extractor: Callable[[Any], dict[str, Any]]


@dataclass(frozen=True)
class ProviderAdapter:
    name: str
    targets: tuple[TargetSpec, ...]


def build_provider_registry() -> tuple[ProviderAdapter, ...]:
    from .anthropic_adapter import get_adapter as get_anthropic_adapter
    from .langchain_adapter import get_adapter as get_langchain_adapter
    from .openai_adapter import get_adapter as get_openai_adapter

    return (
        get_openai_adapter(),
        get_anthropic_adapter(),
        get_langchain_adapter(),
    )


PROVIDER_REGISTRY = build_provider_registry()
