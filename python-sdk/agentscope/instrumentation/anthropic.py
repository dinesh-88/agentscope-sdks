from __future__ import annotations

import importlib.util
from typing import Any, Callable

from .base import BaseInstrumentor, InstrumentationTarget


def is_available() -> bool:
    return importlib.util.find_spec("anthropic") is not None


def _safe_getattr(value: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(value, name, default)
    except Exception:
        return default


def _safe_get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return _safe_getattr(value, key, default)


def _extract_text(response: Any) -> str | None:
    if isinstance(response, dict):
        content = response.get("content")
        if isinstance(content, list):
            parts = [item.get("text") for item in content if isinstance(item, dict)]
            text_parts = [part for part in parts if isinstance(part, str)]
            if text_parts:
                return "".join(text_parts)
        return None

    content = _safe_getattr(response, "content")
    if isinstance(content, list):
        parts = [_safe_getattr(item, "text") for item in content]
        text_parts = [part for part in parts if isinstance(part, str)]
        if text_parts:
            return "".join(text_parts)
    return None


def _request_extractor(
    original: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    bound = BaseInstrumentor.bind_call_args(original, args, kwargs)
    return {
        "model": bound.get("model"),
        "input": {
            "messages": bound.get("messages"),
            "system": bound.get("system"),
        },
    }


def _response_extractor(response: Any) -> dict[str, Any]:
    usage = _safe_get(response, "usage")
    return {
        "output": {
            "text": _extract_text(response),
            "raw": response,
            "usage": {
                "input_tokens": _safe_get(usage, "input_tokens"),
                "output_tokens": _safe_get(usage, "output_tokens"),
                "total_tokens": _safe_get(usage, "total_tokens"),
            },
        }
    }


def get_instrumentors() -> list[BaseInstrumentor]:
    targets = [
        InstrumentationTarget(
            key="anthropic.messages.create",
            provider="anthropic",
            module="anthropic.resources.messages.messages",
            path=("Messages", "create"),
            request_extractor=_request_extractor,
            response_extractor=_response_extractor,
        ),
        InstrumentationTarget(
            key="anthropic.messages.async_create",
            provider="anthropic",
            module="anthropic.resources.messages.messages",
            path=("AsyncMessages", "create"),
            request_extractor=_request_extractor,
            response_extractor=_response_extractor,
        ),
    ]
    return [BaseInstrumentor(target) for target in targets]
