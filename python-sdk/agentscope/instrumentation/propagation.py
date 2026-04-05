from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from ..run import _current_run_state

TRACE_ID_HEADER = "x-agentscope-trace-id"
ROOT_RUN_ID_HEADER = "x-agentscope-root-run-id"
PARENT_RUN_ID_HEADER = "x-agentscope-parent-run-id"
TRACEPARENT_HEADER = "traceparent"


@dataclass(frozen=True)
class TraceContext:
    trace_id: str | None = None
    root_run_id: str | None = None
    parent_run_id: str | None = None

    @property
    def empty(self) -> bool:
        return not (self.trace_id or self.root_run_id or self.parent_run_id)


def current_trace_context() -> TraceContext:
    state = _current_run_state()
    if state is None:
        return TraceContext()

    metadata = state.run.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    trace_id = _coerce_text(metadata.get("trace_id"))
    root_run_id = _coerce_text(metadata.get("root_run_id")) or _coerce_text(state.run.get("id"))
    parent_run_id = _coerce_text(state.run.get("id"))
    return TraceContext(
        trace_id=trace_id,
        root_run_id=root_run_id,
        parent_run_id=parent_run_id,
    )


def extract_from_mapping(headers: dict[str, Any] | None) -> TraceContext:
    if not headers:
        return TraceContext()

    normalized = {str(key).lower(): value for key, value in headers.items()}
    trace_id = _coerce_text(normalized.get(TRACE_ID_HEADER))
    root_run_id = _coerce_text(normalized.get(ROOT_RUN_ID_HEADER))
    parent_run_id = _coerce_text(normalized.get(PARENT_RUN_ID_HEADER))

    if not trace_id:
        traceparent = _coerce_text(normalized.get(TRACEPARENT_HEADER))
        trace_id = _trace_id_from_traceparent(traceparent)

    return TraceContext(
        trace_id=trace_id,
        root_run_id=root_run_id,
        parent_run_id=parent_run_id,
    )


def extract_from_asgi_headers(headers: list[tuple[bytes, bytes]] | None) -> TraceContext:
    if not headers:
        return TraceContext()

    mapping: dict[str, str] = {}
    for raw_key, raw_value in headers:
        try:
            key = raw_key.decode("latin-1").lower()
            value = raw_value.decode("latin-1")
        except Exception:
            continue
        mapping[key] = value

    return extract_from_mapping(mapping)


def inject_into_mapping(
    headers: dict[str, Any] | None,
    *,
    context: TraceContext | None = None,
) -> dict[str, str]:
    next_headers = {str(k): str(v) for k, v in (headers or {}).items()}
    resolved = context or current_trace_context()
    if resolved.empty:
        return next_headers

    if resolved.trace_id:
        next_headers[TRACE_ID_HEADER] = resolved.trace_id
        next_headers[TRACEPARENT_HEADER] = _build_traceparent(resolved.trace_id)
    if resolved.root_run_id:
        next_headers[ROOT_RUN_ID_HEADER] = resolved.root_run_id
    if resolved.parent_run_id:
        next_headers[PARENT_RUN_ID_HEADER] = resolved.parent_run_id
    return next_headers


def inject_into_metadata(
    metadata: list[tuple[str, str]] | None,
    *,
    context: TraceContext | None = None,
) -> list[tuple[str, str]]:
    existing: dict[str, str] = {}
    for key, value in metadata or []:
        existing[str(key)] = str(value)
    injected = inject_into_mapping(existing, context=context)
    return list(injected.items())


def _build_traceparent(trace_id: str) -> str:
    normalized_trace_id = trace_id.replace("-", "").lower()
    if len(normalized_trace_id) != 32:
        normalized_trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]
    return f"00-{normalized_trace_id}-{span_id}-01"


def _trace_id_from_traceparent(traceparent: str | None) -> str | None:
    if not traceparent:
        return None
    parts = traceparent.strip().split("-")
    if len(parts) != 4:
        return None
    trace_hex = parts[1].lower()
    if len(trace_hex) != 32:
        return None
    try:
        return str(uuid.UUID(trace_hex))
    except Exception:
        return None


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None
