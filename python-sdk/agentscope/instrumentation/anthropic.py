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


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    model_dump = _safe_getattr(value, "model_dump")
    if callable(model_dump):
        try:
            return _to_jsonable(model_dump())
        except Exception:
            pass
    to_dict = _safe_getattr(value, "to_dict")
    if callable(to_dict):
        try:
            return _to_jsonable(to_dict())
        except Exception:
            pass
    return repr(value)


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


def _extract_tool_inputs(response: Any) -> list[dict[str, Any]]:
    tool_inputs: list[dict[str, Any]] = []
    content = _safe_get(response, "content")
    if not isinstance(content, list):
        return tool_inputs

    for item in content:
        if _safe_get(item, "type") != "tool_use":
            continue
        tool_inputs.append(
            {
                "id": _safe_get(item, "id"),
                "type": "tool_use",
                "name": _safe_get(item, "name"),
                "arguments": _safe_get(item, "input"),
            }
        )
    return tool_inputs


def _extract_tool_outputs_from_messages(messages: Any) -> list[dict[str, Any]]:
    tool_outputs: list[dict[str, Any]] = []
    if not isinstance(messages, list):
        return tool_outputs

    for message in messages:
        content = _safe_get(message, "content")
        if not isinstance(content, list):
            continue
        for item in content:
            if _safe_get(item, "type") != "tool_result":
                continue
            tool_outputs.append(
                {
                    "id": _safe_get(item, "tool_use_id"),
                    "type": "tool_result",
                    "name": _safe_get(item, "name"),
                    "content": _safe_get(item, "content"),
                }
            )
    return tool_outputs


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
        "tool_outputs": _extract_tool_outputs_from_messages(bound.get("messages")),
    }


def _response_extractor(response: Any) -> dict[str, Any]:
    usage = _safe_get(response, "usage")
    input_tokens = _safe_get(usage, "input_tokens")
    output_tokens = _safe_get(usage, "output_tokens")
    total_tokens = _safe_get(usage, "total_tokens")
    if total_tokens is None and isinstance(input_tokens, int) and isinstance(output_tokens, int):
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "tool_inputs": _extract_tool_inputs(response),
        "output": {
            "text": _extract_text(response),
            "raw": _to_jsonable(response),
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
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
