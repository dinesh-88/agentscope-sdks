from __future__ import annotations

import inspect
from typing import Any, Callable

from .registry import ProviderAdapter, TargetSpec
from .token_usage import normalize_usage


def _safe_getattr(value: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(value, name, default)
    except Exception:
        return default


def _safe_get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return _safe_getattr(value, key, default)


def _extract_call_data(
    original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    try:
        bound = inspect.signature(original).bind_partial(*args, **kwargs)
        data = dict(bound.arguments)
        extra_kwargs = data.pop("kwargs", None)
        if isinstance(extra_kwargs, dict):
            data.update(extra_kwargs)
        return data
    except Exception:
        return dict(kwargs)


def _extract_text(response: Any) -> str | None:
    if isinstance(response, dict):
        content = response.get("content")
        if isinstance(content, list):
            parts = [item.get("text") for item in content if isinstance(item, dict)]
            parts = [part for part in parts if isinstance(part, str)]
            return "".join(parts) if parts else None
        return None

    content = _safe_getattr(response, "content")
    if isinstance(content, list):
        parts = [_safe_getattr(item, "text") for item in content]
        parts = [part for part in parts if isinstance(part, str)]
        return "".join(parts) if parts else None
    return None


def _request_extractor(
    original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    data = _extract_call_data(original, args, kwargs)
    return {
        "model": data.get("model"),
        "messages": data.get("messages"),
        "prompt": data.get("system"),
    }


def _response_extractor(response: Any) -> dict[str, Any]:
    usage = _safe_get(response, "usage")
    input_tokens, output_tokens, total_tokens = normalize_usage(
        _safe_get(usage, "input_tokens"),
        _safe_get(usage, "output_tokens"),
    )
    return {
        "response_text": _extract_text(response),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def get_adapter() -> ProviderAdapter:
    return ProviderAdapter(
        name="anthropic",
        targets=(
            TargetSpec(
                key="anthropic.messages.create",
                provider="anthropic",
                module="anthropic.resources.messages.messages",
                path=("Messages", "create"),
                request_extractor=_request_extractor,
                response_extractor=_response_extractor,
            ),
            TargetSpec(
                key="anthropic.messages.async_create",
                provider="anthropic",
                module="anthropic.resources.messages.messages",
                path=("AsyncMessages", "create"),
                request_extractor=_request_extractor,
                response_extractor=_response_extractor,
            ),
        ),
    )
