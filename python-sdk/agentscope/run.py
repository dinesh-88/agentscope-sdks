from __future__ import annotations

import contextvars
import time
import uuid
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


class observe_run:
    def __init__(
        self,
        workflow_name: str,
        *,
        agent_name: str | None = None,
        project_id: str | None = None,
        exporter: TelemetryExporter | None = None,
    ) -> None:
        self.workflow_name = workflow_name
        self.agent_name = agent_name or workflow_name
        self.project_id = project_id or DEFAULT_PROJECT_ID
        self.exporter = exporter or TelemetryExporter()
        self._run_token: contextvars.Token | None = None
        self._span_token: contextvars.Token | None = None
        self._state: _RunState | None = None

    def __enter__(self) -> Dict[str, Any]:
        run = {
            "id": str(uuid.uuid4()),
            "project_id": self.project_id,
            "workflow_name": self.workflow_name,
            "agent_name": self.agent_name,
            "status": "running",
            "started_at": _iso_utc_now(),
            "ended_at": None,
        }
        self._state = _RunState(run=run, exporter=self.exporter)
        self._run_token = _CURRENT_RUN.set(self._state)
        self._span_token = _SPAN_STACK.set(())
        return run

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._state is None:
            return False

        self._state.run["ended_at"] = _iso_utc_now()
        self._state.run["status"] = "failed" if exc is not None else "success"

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
        except Exception:
            pass
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
