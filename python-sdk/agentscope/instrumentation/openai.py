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


def _extract_tool_calls(response: Any) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []

    choices = _safe_get(response, "choices")
    if isinstance(choices, list):
        for choice in choices:
            message = _safe_get(choice, "message")
            message_tool_calls = _safe_get(message, "tool_calls")
            if isinstance(message_tool_calls, list):
                for call in message_tool_calls:
                    tool_calls.append(
                        {
                            "id": _safe_get(call, "id"),
                            "type": _safe_get(call, "type") or "function",
                            "name": _safe_get(_safe_get(call, "function"), "name"),
                            "arguments": _safe_get(_safe_get(call, "function"), "arguments"),
                        }
                    )

    output = _safe_get(response, "output")
    if isinstance(output, list):
        for item in output:
            if _safe_get(item, "type") in {"function_call", "tool_call"}:
                tool_calls.append(
                    {
                        "id": _safe_get(item, "id") or _safe_get(item, "call_id"),
                        "type": _safe_get(item, "type"),
                        "name": _safe_get(item, "name"),
                        "arguments": _safe_get(item, "arguments"),
                    }
                )

    return tool_calls


def _extract_tool_results_from_input(raw_input: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    if isinstance(raw_input, list):
        for item in raw_input:
            item_type = _safe_get(item, "type")
            if item_type in {"function_call_output", "tool_result"}:
                results.append(
                    {
                        "id": _safe_get(item, "call_id") or _safe_get(item, "id"),
                        "type": item_type,
                        "name": _safe_get(item, "name"),
                        "content": _safe_get(item, "output") or _safe_get(item, "content"),
                    }
                )

    if isinstance(raw_input, str):
        return results

    if isinstance(raw_input, dict):
        item_type = _safe_get(raw_input, "type")
        if item_type in {"function_call_output", "tool_result"}:
            results.append(
                {
                    "id": _safe_get(raw_input, "call_id") or _safe_get(raw_input, "id"),
                    "type": item_type,
                    "name": _safe_get(raw_input, "name"),
                    "content": _safe_get(raw_input, "output") or _safe_get(raw_input, "content"),
                }
            )

    return results


def _extract_tool_results_from_messages(messages: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not isinstance(messages, list):
        return results

    for message in messages:
        if _safe_get(message, "role") != "tool":
            continue
        results.append(
            {
                "id": _safe_get(message, "tool_call_id") or _safe_get(message, "id"),
                "type": "tool_result",
                "name": _safe_get(message, "name"),
                "content": _safe_get(message, "content"),
            }
        )
    return results


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
        "tools": bound.get("tools"),
    }
    tool_outputs = _extract_tool_results_from_input(bound.get("input"))
    tool_outputs.extend(_extract_tool_results_from_messages(bound.get("messages")))
    return {
        "model": bound.get("model"),
        "input": input_payload,
        "tool_outputs": tool_outputs,
    }


def _response_extractor(response: Any) -> dict[str, Any]:
    usage = _safe_get(response, "usage")
    input_tokens = _safe_get(usage, "prompt_tokens") or _safe_get(usage, "input_tokens")
    output_tokens = _safe_get(usage, "completion_tokens") or _safe_get(usage, "output_tokens")
    total_tokens = _safe_get(usage, "total_tokens")
    if total_tokens is None and isinstance(input_tokens, int) and isinstance(output_tokens, int):
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "tool_inputs": _extract_tool_calls(response),
        "output": {
            "text": _extract_text(response),
            "tool_calls": _extract_tool_calls(response),
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
        InstrumentationTarget(
            key="openai.responses.create",
            provider="openai",
            module="openai.resources.responses.responses",
            path=("Responses", "create"),
            request_extractor=_request_extractor,
            response_extractor=_response_extractor,
        ),
        InstrumentationTarget(
            key="openai.responses.async_create",
            provider="openai",
            module="openai.resources.responses.responses",
            path=("AsyncResponses", "create"),
            request_extractor=_request_extractor,
            response_extractor=_response_extractor,
        ),
    ]
    return [BaseInstrumentor(target) for target in targets]
