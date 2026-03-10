from __future__ import annotations

from typing import Any

from ..run import _current_run_state, observe_run
from .llm_tracer import trace_http_llm_call
from .provider_detection import detect_provider

_REQUESTS_PATCHED = False
_ORIGINAL_REQUEST: Any = None


def instrument_requests() -> None:
    global _REQUESTS_PATCHED
    global _ORIGINAL_REQUEST

    if _REQUESTS_PATCHED:
        return

    try:
        import requests
    except Exception:
        return

    current = requests.Session.request
    if getattr(current, "__agentscope_wrapped__", False):
        _REQUESTS_PATCHED = True
        return

    _ORIGINAL_REQUEST = current

    def wrapped_request(self: Any, method: str, url: str, *args: Any, **kwargs: Any) -> Any:
        provider = detect_provider(url)
        if provider is None:
            return _ORIGINAL_REQUEST(self, method, url, *args, **kwargs)

        payload = kwargs.get("json")
        if payload is None:
            payload = {}

        def request_fn() -> Any:
            return _ORIGINAL_REQUEST(self, method, url, *args, **kwargs)

        if _current_run_state() is None:
            with observe_run(f"{provider}_http_auto_instrumentation", agent_name=provider):
                return trace_http_llm_call(provider, url, payload, request_fn)
        return trace_http_llm_call(provider, url, payload, request_fn)

    wrapped_request.__agentscope_wrapped__ = True  # type: ignore[attr-defined]
    requests.Session.request = wrapped_request
    _REQUESTS_PATCHED = True
