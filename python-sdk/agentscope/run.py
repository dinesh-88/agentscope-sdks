from __future__ import annotations

import contextvars
import os
import time
import uuid
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from .exporter import TelemetryExporter

DEFAULT_PROJECT_ID = "00000000-0000-4000-8000-000000000001"

_CURRENT_RUN: contextvars.ContextVar[Optional["_RunState"]] = contextvars.ContextVar(
    "agentscope_current_run",
    default=None,
)
_SPAN_STACK: contextvars.ContextVar[Tuple[str, ...]] = contextvars.ContextVar(
    "agentscope_span_stack",
    default=(),
)


def _iso_utc_now() -> str:
    now = time.time()
    seconds = int(now)
    millis = int((now - seconds) * 1000)
    return f"{time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(seconds))}.{millis:03d}Z"


@dataclass
class _RunState:
    run: Dict[str, Any]
    spans: list[Dict[str, Any]] = field(default_factory=list)
    artifacts: list[Dict[str, Any]] = field(default_factory=list)
    exporter: TelemetryExporter = field(default_factory=TelemetryExporter)
    live_stream_enabled: bool = True


class observe_run:
    def __init__(
        self,
        workflow_name: str,
        *,
        agent_name: str | None = None,
        project_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        environment: str | None = None,
        tags: list[str] | None = None,
        experiment_id: str | None = None,
        variant: str | None = None,
        metadata: Dict[str, Any] | None = None,
        exporter: TelemetryExporter | None = None,
        live_stream: bool | None = None,
    ) -> None:
        self.workflow_name = workflow_name
        self.agent_name = agent_name or workflow_name
        self.project_id = project_id or DEFAULT_PROJECT_ID
        self.user_id = user_id
        self.session_id = session_id
        self.environment = environment
        self.tags = tags
        self.experiment_id = experiment_id
        self.variant = variant
        self.metadata = metadata
        self.exporter = exporter or TelemetryExporter()
        self.live_stream = _env_live_stream_default() if live_stream is None else live_stream
        self._run_token: contextvars.Token | None = None
        self._span_token: contextvars.Token | None = None
        self._state: _RunState | None = None

    def __enter__(self) -> Dict[str, Any]:
        run = {
            "id": str(uuid.uuid4()),
            "project_id": self.project_id,
            "organization_id": None,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "environment": self.environment,
            "workflow_name": self.workflow_name,
            "agent_name": self.agent_name,
            "status": "running",
            "started_at": _iso_utc_now(),
            "ended_at": None,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "success": None,
            "error_count": 0,
            "avg_latency_ms": None,
            "p95_latency_ms": None,
            "success_rate": None,
            "tags": self.tags,
            "experiment_id": self.experiment_id,
            "variant": self.variant,
            "metadata": self.metadata,
        }
        self._state = _RunState(run=run, exporter=self.exporter, live_stream_enabled=self.live_stream)
        self._run_token = _CURRENT_RUN.set(self._state)
        self._span_token = _SPAN_STACK.set(())
        _safe_live_flush(self._state)
        return run

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._state is None:
            return False

        self._state.run["ended_at"] = _iso_utc_now()
        self._state.run["status"] = "failed" if exc is not None else "success"
        self._state.run["success"] = exc is None

        if exc is not None:
            self._state.artifacts.append(
                {
                    "id": str(uuid.uuid4()),
                    "run_id": self._state.run["id"],
                    "span_id": None,
                    "kind": "error",
                    "payload": {"error_type": exc_type.__name__ if exc_type else "Exception", "message": str(exc)},
                }
            )

        try:
            self._state.exporter.export(self._state.run, self._state.spans, self._state.artifacts)
        except Exception as export_error:
            warnings.warn(
                f"AgentScope export failed: {export_error}",
                RuntimeWarning,
                stacklevel=2,
            )
        finally:
            if self._span_token is not None:
                _SPAN_STACK.reset(self._span_token)
            if self._run_token is not None:
                _CURRENT_RUN.reset(self._run_token)

        return False


def _current_run_state() -> _RunState | None:
    return _CURRENT_RUN.get()


def _push_span(span_id: str) -> contextvars.Token:
    stack = _SPAN_STACK.get()
    return _SPAN_STACK.set(stack + (span_id,))


def _pop_span(token: contextvars.Token) -> None:
    _SPAN_STACK.reset(token)


def _current_parent_span_id() -> str | None:
    stack = _SPAN_STACK.get()
    return stack[-1] if stack else None


def _env_live_stream_default() -> bool:
    raw = os.getenv("AGENTSCOPE_LIVE_STREAM", "true").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _safe_live_flush(state: _RunState | None) -> None:
    if state is None or not state.live_stream_enabled:
        return

    try:
        state.exporter.export(state.run, state.spans, state.artifacts)
    except Exception as export_error:
        warnings.warn(
            f"AgentScope live export failed: {export_error}",
            RuntimeWarning,
            stacklevel=2,
        )


def _append_artifact(kind: str, payload: Dict[str, Any], *, span_id: str | None = None) -> Dict[str, Any]:
    state = _current_run_state()
    if state is None:
        raise RuntimeError("trace APIs must be used inside observe_run")

    artifact = {
        "id": str(uuid.uuid4()),
        "run_id": state.run["id"],
        "span_id": span_id,
        "kind": kind,
        "payload": payload,
    }
    state.artifacts.append(artifact)
    _safe_live_flush(state)
    return artifact


def _update_span(span_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    state = _current_run_state()
    if state is None:
        raise RuntimeError("trace APIs must be used inside observe_run")

    span = next((entry for entry in state.spans if entry["id"] == span_id), None)
    if span is None:
        raise ValueError(f"span {span_id} not found in current run")

    span.update(data)
    _safe_live_flush(state)
    return span
