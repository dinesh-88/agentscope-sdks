from __future__ import annotations

import contextvars
import uuid
from typing import Any, Dict

from .run import _current_parent_span_id, _current_run_state, _iso_utc_now, _pop_span, _push_span


class observe_span:
    def __init__(self, name: str, *, span_type: str | None = None) -> None:
        self.name = name
        self.span_type = span_type or name
        self._span: Dict[str, Any] | None = None
        self._span_token: contextvars.Token | None = None

    def __enter__(self) -> Dict[str, Any]:
        run_state = _current_run_state()
        if run_state is None:
            raise RuntimeError("observe_span must be used inside observe_run")

        self._span = {
            "id": str(uuid.uuid4()),
            "run_id": run_state.run["id"],
            "parent_span_id": _current_parent_span_id(),
            "span_type": self.span_type,
            "name": self.name,
            "status": "running",
            "started_at": _iso_utc_now(),
            "ended_at": None,
            "metadata": None,
        }
        run_state.spans.append(self._span)
        self._span_token = _push_span(self._span["id"])
        return self._span

    def __exit__(self, exc_type, exc, tb) -> bool:
        run_state = _current_run_state()
        if self._span is None:
            return False

        self._span["ended_at"] = _iso_utc_now()
        self._span["status"] = "failed" if exc is not None else "success"

        if exc is not None and run_state is not None:
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
        return False
