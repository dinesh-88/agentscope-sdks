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
        choices = response.get("choices")
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content")
            if isinstance(content, str):
                return content
        output_text = response.get("output_text")
        if isinstance(output_text, str):
            return output_text
        text = response.get("response")
        if isinstance(text, str):
            return text
        return None

    choices = _safe_getattr(response, "choices")
    if choices:
        message = _safe_getattr(choices[0], "message")
        content = _safe_getattr(message, "content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [_safe_getattr(item, "text") for item in content]
            parts = [part for part in parts if isinstance(part, str)]
            if parts:
                return "".join(parts)

    output_text = _safe_getattr(response, "output_text")
    if isinstance(output_text, str):
        return output_text
    text = _safe_getattr(response, "response")
    if isinstance(text, str):
        return text
    return None


def _request_extractor(
    original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    data = _extract_call_data(original, args, kwargs)
    return {
        "model": data.get("model"),
        "messages": data.get("messages") or data.get("input"),
        "prompt": data.get("prompt") or data.get("input"),
    }


def _response_extractor(response: Any) -> dict[str, Any]:
    usage = _safe_get(response, "usage")
    input_tokens = _safe_get(usage, "prompt_tokens")
    if input_tokens is None:
        input_tokens = _safe_get(usage, "input_tokens")
    output_tokens = _safe_get(usage, "completion_tokens")
    if output_tokens is None:
        output_tokens = _safe_get(usage, "output_tokens")
    input_tokens, output_tokens, total_tokens = normalize_usage(input_tokens, output_tokens)
    return {
        "response_text": _extract_text(response),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def get_adapter() -> ProviderAdapter:
    return ProviderAdapter(
        name="openai",
        targets=(
            TargetSpec(
                key="openai.chat.completions.create",
                provider="openai",
                module="openai.resources.chat.completions.completions",
                path=("Completions", "create"),
                request_extractor=_request_extractor,
                response_extractor=_response_extractor,
            ),
            TargetSpec(
                key="openai.chat.completions.async_create",
                provider="openai",
                module="openai.resources.chat.completions.completions",
                path=("AsyncCompletions", "create"),
                request_extractor=_request_extractor,
                response_extractor=_response_extractor,
            ),
        ),
    )
