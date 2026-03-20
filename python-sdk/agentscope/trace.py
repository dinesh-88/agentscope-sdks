from __future__ import annotations

from typing import Any, Dict

from .instrumentation import auto_trace
from .run import _append_artifact, _current_parent_span_id, _update_span


class _TraceFacade:
    def auto(self, providers: list[str] | None = None) -> None:
        auto_trace(providers=providers)

    def log(
        self,
        message: str,
        *,
        level: str = "info",
        span_id: str | None = None,
        metadata: Dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> Dict[str, Any]:
        resolved_span_id = span_id or _current_parent_span_id()
        payload: Dict[str, Any] = {
            "message": message,
            "level": level,
        }
        if metadata is not None:
            payload["metadata"] = metadata
        if timestamp is not None:
            payload["timestamp"] = timestamp

        return _append_artifact("log", payload, span_id=resolved_span_id)

    def update_span(self, span_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return _update_span(span_id, data)


trace = _TraceFacade()

