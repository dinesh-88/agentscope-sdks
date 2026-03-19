from __future__ import annotations

import inspect
import time
import uuid
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable

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
