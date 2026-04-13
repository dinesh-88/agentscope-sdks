from __future__ import annotations

import time
import uuid
from typing import Any, Callable

from ..context_manager import trace_context
from ..run import _current_run_state
from ..span import observe_span
from .token_usage import normalize_usage


def _extract_response_text(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None

    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message")
        if isinstance(message, dict):
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

    content = body.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            text = first.get("text")
            if isinstance(text, str):
                return text

    response = body.get("response")
    if isinstance(response, str):
        return response

    output = body.get("output")
    if isinstance(output, str):
        return output

    return None


def _extract_usage(body: Any) -> tuple[int | None, int | None, int | None]:
    if not isinstance(body, dict):
        return None, None, None

    usage = body.get("usage")
    if not isinstance(usage, dict):
        return None, None, None

    input_tokens = usage.get("prompt_tokens")
    if input_tokens is None:
        input_tokens = usage.get("input_tokens")

    output_tokens = usage.get("completion_tokens")
    if output_tokens is None:
        output_tokens = usage.get("output_tokens")

    return normalize_usage(input_tokens, output_tokens)


def _append_artifact(*, span: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    run_state = _current_run_state()
    if run_state is None:
        return

    run_state.artifacts.append(
        {
            "id": str(uuid.uuid4()),
            "run_id": span["run_id"],
            "span_id": span["id"],
            "kind": kind,
            "payload": payload,
        }
    )


def _append_context_snapshot_artifact(*, span: dict[str, Any], final_prompt: Any) -> None:
    sources = trace_context.get_all()
    if not sources:
        return

    _append_artifact(
        span=span,
        kind="llm.context",
        payload={
            "data": {
                "sources": sources,
                "final_prompt": final_prompt,
            }
        },
    )


def _extract_prompt_fields(payload: Any) -> tuple[Any, Any, Any]:
    if not isinstance(payload, dict):
        return None, None, None

    messages = payload.get("messages")
    prompt = payload.get("prompt")
    if prompt is None:
        prompt = payload.get("input")
    return messages, prompt, payload.get("input")


def _message_content_to_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts) if parts else None
    return None


def _normalize_messages(raw: Any) -> list[dict[str, Any]] | None:
    if not isinstance(raw, list):
        return None
    return [item for item in raw if isinstance(item, dict)]


def _extract_system_user_text(messages: Any, input_value: Any) -> tuple[str | None, str | None]:
    normalized = _normalize_messages(messages)
    if normalized:
        system_parts: list[str] = []
        user_parts: list[str] = []
        for message in normalized:
            role = str(message.get("role", "")).lower()
            content = _message_content_to_text(message.get("content"))
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
            if role == "user":
                user_parts.append(content)
        return ("\n".join(system_parts) if system_parts else None, "\n".join(user_parts) if user_parts else None)
    if isinstance(input_value, str):
        return None, input_value
    normalized_input = _normalize_messages(input_value)
    if normalized_input:
        return _extract_system_user_text(normalized_input, None)
    return None, None


def trace_http_llm_call(
    provider: str,
    url: str,
    payload: Any,
    request_fn: Callable[[], Any],
) -> Any:
    started = time.perf_counter()
    with observe_span("llm_call", span_type="llm_call") as span:
        span["provider"] = provider
        span["endpoint_url"] = url
        span["model"] = payload.get("model") if isinstance(payload, dict) else None
        messages, prompt, input_value = _extract_prompt_fields(payload)
        system_prompt, user_input = _extract_system_user_text(messages, input_value)

        _append_artifact(
            span=span,
            kind="llm.prompt",
            payload={
                "provider": provider,
                "endpoint_url": url,
                "model": span.get("model"),
                "messages": messages,
                "prompt": prompt,
                "input": input_value,
                "system_prompt": system_prompt,
                "user_input": user_input,
                "payload": payload,
            },
        )
        _append_context_snapshot_artifact(span=span, final_prompt=payload)

        response = request_fn()
        latency_ms = int((time.perf_counter() - started) * 1000)

        response_body: Any = None
        try:
            response_body = response.json()
        except Exception:
            response_body = None

        response_text = _extract_response_text(response_body)
        input_tokens, output_tokens, total_tokens = _extract_usage(response_body)
        http_status = getattr(response, "status_code", None)

        span["latency_ms"] = latency_ms
        span["input_tokens"] = input_tokens
        span["output_tokens"] = output_tokens
        span["total_tokens"] = total_tokens

        _append_artifact(
            span=span,
            kind="llm.response",
            payload={
                "provider": provider,
                "endpoint_url": url,
                "model": span.get("model"),
                "response": response_body,
                "response_text": response_text,
                "http_status": http_status,
                "latency_ms": latency_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                },
            },
        )

        return response
