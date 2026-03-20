from __future__ import annotations

import contextvars
import hashlib
import json
import time
import uuid
from typing import Any, Dict

from .run import (
    _current_parent_span_id,
    _current_run_state,
    _iso_utc_now,
    _pop_span,
    _push_span,
    _safe_live_flush,
)


class observe_span:
    def __init__(
        self,
        name: str,
        *,
        span_type: str | None = None,
        metadata: Dict[str, Any] | None = None,
        error: Dict[str, Any] | None = None,
        evaluation: Dict[str, Any] | None = None,
        prompt: str | None = None,
        prompt_template_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        estimated_cost: float | None = None,
        context_window: int | None = None,
        context_usage_percent: float | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        retry_attempt: int | None = None,
        max_attempts: int | None = None,
        tool_name: str | None = None,
        tool_version: str | None = None,
        tool_latency_ms: float | None = None,
        tool_success: bool | None = None,
        response_text: str | None = None,
    ) -> None:
        self.name = name
        self.span_type = span_type or name
        self.metadata = metadata
        self.error = error
        self.evaluation = evaluation
        self.prompt = prompt
        self.prompt_template_id = prompt_template_id
        self.provider = provider
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = total_tokens
        self.estimated_cost = estimated_cost
        self.context_window = context_window
        self.context_usage_percent = context_usage_percent
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.retry_attempt = retry_attempt
        self.max_attempts = max_attempts
        self.tool_name = tool_name
        self.tool_version = tool_version
        self.tool_latency_ms = tool_latency_ms
        self.tool_success = tool_success
        self.response_text = response_text
        self._span: Dict[str, Any] | None = None
        self._span_token: contextvars.Token | None = None
        self._started_monotonic = 0.0

    def __enter__(self) -> Dict[str, Any]:
        run_state = _current_run_state()
        if run_state is None:
            raise RuntimeError("observe_span must be used inside observe_run")

        self._started_monotonic = time.monotonic()
        self._span = {
            "id": str(uuid.uuid4()),
            "run_id": run_state.run["id"],
            "parent_span_id": _current_parent_span_id(),
            "span_type": self.span_type,
            "name": self.name,
            "status": "running",
            "started_at": _iso_utc_now(),
            "ended_at": None,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
            "context_window": self.context_window,
            "context_usage_percent": self.context_usage_percent,
            "latency_ms": None,
            "success": None,
            "error_type": self.error.get("error_type") if self.error else None,
            "error_source": self.error.get("error_source") if self.error else None,
            "retryable": self.error.get("retryable") if self.error else None,
            "prompt_hash": _prompt_hash(self.prompt) if self.prompt else None,
            "prompt_template_id": self.prompt_template_id,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "retry_attempt": self.retry_attempt,
            "max_attempts": self.max_attempts,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "tool_latency_ms": self.tool_latency_ms,
            "tool_success": self.tool_success,
            "evaluation": self.evaluation or _evaluate_response(self.response_text),
            "metadata": self.metadata,
            "error": self.error,
        }
        run_state.spans.append(self._span)
        self._span_token = _push_span(self._span["id"])
        _safe_live_flush(run_state)
        return self._span

    def __exit__(self, exc_type, exc, tb) -> bool:
        run_state = _current_run_state()
        if self._span is None:
            return False

        self._span["ended_at"] = _iso_utc_now()
        self._span["status"] = "failed" if exc is not None else "success"
        self._span["success"] = exc is None
        elapsed = (time.monotonic() - self._started_monotonic) * 1000.0
        self._span["latency_ms"] = max(0.0, elapsed)

        if exc is not None and run_state is not None:
            self._span["error_type"] = self._span.get("error_type") or "unknown"
            self._span["error_source"] = self._span.get("error_source") or "system"
            run_state.artifacts.append(
                {
                    "id": str(uuid.uuid4()),
                    "run_id": self._span["run_id"],
                    "span_id": self._span["id"],
                    "kind": "error",
                    "payload": {"error_type": exc_type.__name__ if exc_type else "Exception", "message": str(exc)},
                }
            )

        if self._span_token is not None:
            _pop_span(self._span_token)
        _safe_live_flush(run_state)
        return False


def _prompt_hash(prompt: str) -> str:
    normalized = " ".join(prompt.replace("\r\n", "\n").strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _evaluate_response(response_text: str | None) -> Dict[str, Any] | None:
    if response_text is None:
        return None

    stripped = response_text.strip()
    if not stripped:
        return {
            "success": False,
            "score": 0.0,
            "reason": "Empty response",
            "evaluator": "rule",
        }

    try:
        json.loads(stripped)
        return {
            "success": True,
            "score": 1.0,
            "reason": "Valid JSON response",
            "evaluator": "rule",
        }
    except Exception:
        return {
            "success": False,
            "score": 0.0,
            "reason": "Invalid JSON response",
            "evaluator": "rule",
        }
