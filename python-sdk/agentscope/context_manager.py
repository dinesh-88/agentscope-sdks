from __future__ import annotations

import contextlib
import contextvars
import hashlib
from typing import Any

_CONTEXT_SOURCES: contextvars.ContextVar[tuple[dict[str, str], ...]] = contextvars.ContextVar(
    "agentscope_context_sources",
    default=(),
)

_VALID_SOURCE_TYPES = {"file", "runtime"}


def _compute_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@contextlib.contextmanager
def _noop_scope(_name: str) -> Any:
    yield


class TraceContextManager:
    def add(self, name: str, content: str, type: str = "file") -> dict[str, str]:
        if type not in _VALID_SOURCE_TYPES:
            raise ValueError("type must be one of: file, runtime")

        source = {
            "name": name,
            "type": type,
            "content": content,
            "hash": _compute_sha256(content),
        }
        current = _CONTEXT_SOURCES.get()
        _CONTEXT_SOURCES.set(current + (source,))
        return dict(source)

    def clear(self) -> None:
        _CONTEXT_SOURCES.set(())

    def get_all(self) -> list[dict[str, str]]:
        return [dict(source) for source in _CONTEXT_SOURCES.get()]

    def scope(self, name: str) -> Any:
        return _noop_scope(name)


trace_context = TraceContextManager()

