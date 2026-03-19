from __future__ import annotations

import importlib.util
from typing import Any, Callable

from .base import BaseInstrumentor, InstrumentationTarget


def is_available() -> bool:
    return importlib.util.find_spec("openai") is not None


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
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [part.get("text") for part in content if isinstance(part, dict)]
                text_parts = [part for part in parts if isinstance(part, str)]
                if text_parts:
                    return "".join(text_parts)
            text = choices[0].get("text")
            if isinstance(text, str):
                return text

        output_text = response.get("output_text")
        if isinstance(output_text, str):
            return output_text

        output = response.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if isinstance(item, dict):
                    content = item.get("content")
                    if isinstance(content, list):
                        for content_item in content:
                            if isinstance(content_item, dict):
                                text = content_item.get("text")
                                if isinstance(text, str):
                                    parts.append(text)
            if parts:
                return "".join(parts)
        return None

    choices = _safe_getattr(response, "choices")
    if isinstance(choices, list) and choices:
        message = _safe_getattr(choices[0], "message")
        content = _safe_getattr(message, "content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [_safe_getattr(item, "text") for item in content]
            text_parts = [part for part in parts if isinstance(part, str)]
            if text_parts:
                return "".join(text_parts)

        text = _safe_getattr(choices[0], "text")
        if isinstance(text, str):
            return text

    output_text = _safe_getattr(response, "output_text")
    if isinstance(output_text, str):
        return output_text

    output = _safe_getattr(response, "output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            content = _safe_getattr(item, "content")
            if isinstance(content, list):
                for content_item in content:
                    text = _safe_getattr(content_item, "text")
                    if isinstance(text, str):
                        parts.append(text)
        if parts:
            return "".join(parts)

    return None


def _request_extractor(
    original: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    bound = BaseInstrumentor.bind_call_args(original, args, kwargs)
    input_payload = {
        "messages": bound.get("messages"),
        "prompt": bound.get("prompt"),
        "input": bound.get("input"),
    }
    return {
        "model": bound.get("model"),
        "input": input_payload,
    }


def _response_extractor(response: Any) -> dict[str, Any]:
    usage = _safe_get(response, "usage")
    return {
        "output": {
            "text": _extract_text(response),
            "raw": response,
            "usage": {
                "input_tokens": _safe_get(usage, "prompt_tokens") or _safe_get(usage, "input_tokens"),
                "output_tokens": _safe_get(usage, "completion_tokens") or _safe_get(usage, "output_tokens"),
                "total_tokens": _safe_get(usage, "total_tokens"),
            },
        }
    }


def get_instrumentors() -> list[BaseInstrumentor]:
    targets = [
        InstrumentationTarget(
            key="openai.chat.completions.create",
            provider="openai",
            module="openai.resources.chat.completions.completions",
            path=("Completions", "create"),
            request_extractor=_request_extractor,
            response_extractor=_response_extractor,
        ),
        InstrumentationTarget(
            key="openai.chat.completions.async_create",
            provider="openai",
            module="openai.resources.chat.completions.completions",
            path=("AsyncCompletions", "create"),
            request_extractor=_request_extractor,
            response_extractor=_response_extractor,
        ),
    ]
    return [BaseInstrumentor(target) for target in targets]
