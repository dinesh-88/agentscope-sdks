from __future__ import annotations

import time
import uuid
from typing import Any, Callable

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


def _extract_prompt_fields(payload: Any) -> tuple[Any, Any, Any]:
    if not isinstance(payload, dict):
        return None, None, None

    messages = payload.get("messages")
    prompt = payload.get("prompt")
    if prompt is None:
        prompt = payload.get("input")
    return messages, prompt, payload.get("input")


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
                "payload": payload,
            },
        )

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
            },
        )

        return response
