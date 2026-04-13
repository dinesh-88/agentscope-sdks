from __future__ import annotations

import inspect
import time
import uuid
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable

from ..context_manager import trace_context
from ..run import _current_run_state, observe_run
from ..span import observe_span


@dataclass(frozen=True)
class LLMCallRecord:
    provider: str
    model: str | None
    input: Any
    output: Any
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    tool_inputs: list[dict[str, Any]] | None = None
    tool_outputs: list[dict[str, Any]] | None = None
    error: dict[str, str] | None = None


@dataclass(frozen=True)
class InstrumentationTarget:
    key: str
    provider: str
    module: str
    path: tuple[str, ...]
    request_extractor: Callable[[Callable[..., Any], tuple[Any, ...], dict[str, Any]], dict[str, Any]]
    response_extractor: Callable[[Any], dict[str, Any]]


class BaseInstrumentor:
    def __init__(self, target: InstrumentationTarget) -> None:
        self.target = target
        self._patched = False

    @staticmethod
    def bind_call_args(
        original: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
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

    def patch(self, module: Any) -> bool:
        if self._patched:
            return False

        resolved = self._resolve_parent(module, self.target.path)
        if resolved is None:
            return False

        parent, attr_name = resolved
        current = getattr(parent, attr_name, None)
        if current is None:
            return False

        if getattr(current, "__agentscope_wrapped__", False):
            self._patched = True
            return False

        setattr(parent, attr_name, self._build_wrapper(current))
        self._patched = True
        return True

    def _resolve_parent(self, module: Any, path: tuple[str, ...]) -> tuple[Any, str] | None:
        if not path:
            return None

        parent = module
        for part in path[:-1]:
            parent = getattr(parent, part, None)
            if parent is None:
                return None
        return parent, path[-1]

    def _build_wrapper(self, original: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(original):

            @wraps(original)
            async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if _current_run_state() is None:
                    with observe_run(f"{self.target.provider}_auto_trace", agent_name=self.target.provider):
                        return await self._run_async(original=original, args=args, kwargs=kwargs)
                return await self._run_async(original=original, args=args, kwargs=kwargs)

            _async_wrapper.__agentscope_wrapped__ = True  # type: ignore[attr-defined]
            return _async_wrapper

        @wraps(original)
        def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            if _current_run_state() is None:
                with observe_run(f"{self.target.provider}_auto_trace", agent_name=self.target.provider):
                    return self._run_sync(original=original, args=args, kwargs=kwargs)
            return self._run_sync(original=original, args=args, kwargs=kwargs)

        _sync_wrapper.__agentscope_wrapped__ = True  # type: ignore[attr-defined]
        return _sync_wrapper

    def _run_sync(self, *, original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        request = self.target.request_extractor(original, args, kwargs)
        started = time.perf_counter()

        with observe_span("llm_call", span_type="llm_call") as span:
            try:
                response = original(*args, **kwargs)
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                self._apply_span(
                    span=span,
                    record=LLMCallRecord(
                        provider=self.target.provider,
                        model=request.get("model"),
                        input=request.get("input"),
                        output=None,
                        latency_ms=latency_ms,
                        tool_outputs=request.get("tool_outputs"),
                        error={"type": exc.__class__.__name__, "message": str(exc)},
                    ),
                )
                raise

            response_data = self.target.response_extractor(response)
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._apply_span(
                span=span,
                record=LLMCallRecord(
                    provider=self.target.provider,
                    model=request.get("model"),
                    input=request.get("input"),
                    output=response_data.get("output"),
                    latency_ms=latency_ms,
                    input_tokens=response_data.get("input_tokens"),
                    output_tokens=response_data.get("output_tokens"),
                    total_tokens=response_data.get("total_tokens"),
                    tool_inputs=response_data.get("tool_inputs"),
                    tool_outputs=response_data.get("tool_outputs") or request.get("tool_outputs"),
                ),
            )
            return response

    async def _run_async(
        self,
        *,
        original: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        request = self.target.request_extractor(original, args, kwargs)
        started = time.perf_counter()

        with observe_span("llm_call", span_type="llm_call") as span:
            try:
                response = await original(*args, **kwargs)
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                self._apply_span(
                    span=span,
                    record=LLMCallRecord(
                        provider=self.target.provider,
                        model=request.get("model"),
                        input=request.get("input"),
                        output=None,
                        latency_ms=latency_ms,
                        tool_outputs=request.get("tool_outputs"),
                        error={"type": exc.__class__.__name__, "message": str(exc)},
                    ),
                )
                raise

            response_data = self.target.response_extractor(response)
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._apply_span(
                span=span,
                record=LLMCallRecord(
                    provider=self.target.provider,
                    model=request.get("model"),
                    input=request.get("input"),
                    output=response_data.get("output"),
                    latency_ms=latency_ms,
                    input_tokens=response_data.get("input_tokens"),
                    output_tokens=response_data.get("output_tokens"),
                    total_tokens=response_data.get("total_tokens"),
                    tool_inputs=response_data.get("tool_inputs"),
                    tool_outputs=response_data.get("tool_outputs") or request.get("tool_outputs"),
                ),
            )
            return response

    @staticmethod
    def _apply_span(span: dict[str, Any], record: LLMCallRecord) -> None:
        run_state = _current_run_state()
        span["provider"] = record.provider
        span["model"] = record.model
        span["latency_ms"] = record.latency_ms
        span["input_tokens"] = record.input_tokens
        span["output_tokens"] = record.output_tokens
        span["total_tokens"] = record.total_tokens
        span["metadata"] = {
            "schema": "agentscope.llm_call.v1",
            "provider": record.provider,
            "model": record.model,
            "input": record.input,
            "output": record.output,
            "latency_ms": record.latency_ms,
            "input_tokens": record.input_tokens,
            "output_tokens": record.output_tokens,
            "total_tokens": record.total_tokens,
            "tool_inputs": record.tool_inputs or [],
            "tool_outputs": record.tool_outputs or [],
            "error": record.error,
        }
        if run_state is None:
            return

        system_prompt = None
        user_input = None
        if isinstance(record.input, dict):
            messages = record.input.get("messages")
            prompt = record.input.get("prompt")
            input_value = record.input.get("input")
            system_prompt, user_input = _extract_system_user_text(messages, input_value)
            if system_prompt is None and isinstance(prompt, str):
                system_prompt = prompt
        else:
            system_prompt, user_input = _extract_system_user_text(None, record.input)

        sources = trace_context.get_all()
        if sources:
            run_state.artifacts.append(
                {
                    "id": str(uuid.uuid4()),
                    "run_id": span["run_id"],
                    "span_id": span["id"],
                    "kind": "llm.context",
                    "payload": {
                        "data": {
                            "sources": sources,
                            "final_prompt": record.input,
                        }
                    },
                }
            )

        run_state.artifacts.append(
            {
                "id": str(uuid.uuid4()),
                "run_id": span["run_id"],
                "span_id": span["id"],
                "kind": "llm.prompt",
                "payload": {
                    "provider": record.provider,
                    "model": record.model,
                    "input": record.input,
                    "system_prompt": system_prompt,
                    "user_input": user_input,
                },
            }
        )
        run_state.artifacts.append(
            {
                "id": str(uuid.uuid4()),
                "run_id": span["run_id"],
                "span_id": span["id"],
                "kind": "llm.response",
                "payload": {
                    "provider": record.provider,
                    "model": record.model,
                    "output": record.output,
                    "latency_ms": record.latency_ms,
                    "input_tokens": record.input_tokens,
                    "output_tokens": record.output_tokens,
                    "total_tokens": record.total_tokens,
                    "usage": {
                        "input_tokens": record.input_tokens,
                        "output_tokens": record.output_tokens,
                        "total_tokens": record.total_tokens,
                        "prompt_tokens": record.input_tokens,
                        "completion_tokens": record.output_tokens,
                    },
                    "error": record.error,
                },
            }
        )
        for tool_input in record.tool_inputs or []:
            run_state.artifacts.append(
                {
                    "id": str(uuid.uuid4()),
                    "run_id": span["run_id"],
                    "span_id": span["id"],
                    "kind": "tool.input",
                    "payload": {
                        "provider": record.provider,
                        "model": record.model,
                        **tool_input,
                    },
                }
            )
        for tool_output in record.tool_outputs or []:
            run_state.artifacts.append(
                {
                    "id": str(uuid.uuid4()),
                    "run_id": span["run_id"],
                    "span_id": span["id"],
                    "kind": "tool.output",
                    "payload": {
                        "provider": record.provider,
                        "model": record.model,
                        **tool_output,
                    },
                }
            )


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
