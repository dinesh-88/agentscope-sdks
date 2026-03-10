from __future__ import annotations

import builtins
import inspect
import sys
import time
import uuid
from functools import wraps
from typing import Any, Callable

from ..run import _current_run_state, observe_run
from ..span import observe_span
from .http_interceptor import instrument_requests
from .registry import PROVIDER_REGISTRY, TargetSpec
from .token_usage import normalize_usage

_ORIGINALS: dict[str, Callable[..., Any]] = {}
_PATCHED_TARGETS: set[str] = set()
_ACTIVE_TARGETS: list[TargetSpec] = []
_IMPORT_HOOK_INSTALLED = False
_ORIGINAL_IMPORT = builtins.__import__


def _append_artifacts(
    *,
    span: dict[str, Any],
    provider: str,
    model: Any,
    messages: Any,
    prompt: Any,
    response_text: Any,
    input_tokens: Any,
    output_tokens: Any,
    total_tokens: Any,
    latency_ms: int,
) -> None:
    run_state = _current_run_state()
    if run_state is None:
        return

    run_state.artifacts.append(
        {
            "id": str(uuid.uuid4()),
            "run_id": span["run_id"],
            "span_id": span["id"],
            "kind": "llm_prompt",
            "payload": {
                "provider": provider,
                "model": model,
                "messages": messages,
                "prompt": prompt,
            },
        }
    )
    run_state.artifacts.append(
        {
            "id": str(uuid.uuid4()),
            "run_id": span["run_id"],
            "span_id": span["id"],
            "kind": "llm_response",
            "payload": {
                "provider": provider,
                "model": model,
                "response_text": response_text,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "latency_ms": latency_ms,
            },
        }
    )


def _run_instrumented_sync(
    *,
    target: TargetSpec,
    original: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    req = target.request_extractor(original, args, kwargs)
    started = time.time()
    with observe_span("llm_call", span_type="llm_call") as span:
        response = original(*args, **kwargs)
        res = target.response_extractor(response)
        latency_ms = int((time.time() - started) * 1000)
        input_tokens, output_tokens, total_tokens = normalize_usage(
            res.get("input_tokens"),
            res.get("output_tokens"),
        )

        span["provider"] = target.provider
        span["model"] = req.get("model")
        span["input_tokens"] = input_tokens
        span["output_tokens"] = output_tokens
        span["total_tokens"] = total_tokens
        span["latency_ms"] = latency_ms

        _append_artifacts(
            span=span,
            provider=target.provider,
            model=req.get("model"),
            messages=req.get("messages"),
            prompt=req.get("prompt"),
            response_text=res.get("response_text"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
        return response


async def _run_instrumented_async(
    *,
    target: TargetSpec,
    original: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    req = target.request_extractor(original, args, kwargs)
    started = time.time()
    with observe_span("llm_call", span_type="llm_call") as span:
        response = await original(*args, **kwargs)
        res = target.response_extractor(response)
        latency_ms = int((time.time() - started) * 1000)
        input_tokens, output_tokens, total_tokens = normalize_usage(
            res.get("input_tokens"),
            res.get("output_tokens"),
        )

        span["provider"] = target.provider
        span["model"] = req.get("model")
        span["input_tokens"] = input_tokens
        span["output_tokens"] = output_tokens
        span["total_tokens"] = total_tokens
        span["latency_ms"] = latency_ms

        _append_artifacts(
            span=span,
            provider=target.provider,
            model=req.get("model"),
            messages=req.get("messages"),
            prompt=req.get("prompt"),
            response_text=res.get("response_text"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
        return response


def _build_wrapper(original: Callable[..., Any], target: TargetSpec) -> Callable[..., Any]:
    if inspect.iscoroutinefunction(original):

        @wraps(original)
        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            if _current_run_state() is None:
                with observe_run(f"{target.provider}_auto_instrumentation", agent_name=target.provider):
                    return await _run_instrumented_async(
                        target=target,
                        original=original,
                        args=args,
                        kwargs=kwargs,
                    )
            return await _run_instrumented_async(target=target, original=original, args=args, kwargs=kwargs)

        _async_wrapper.__agentscope_wrapped__ = True  # type: ignore[attr-defined]
        return _async_wrapper

    @wraps(original)
    def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        if _current_run_state() is None:
            with observe_run(f"{target.provider}_auto_instrumentation", agent_name=target.provider):
                return _run_instrumented_sync(target=target, original=original, args=args, kwargs=kwargs)
        return _run_instrumented_sync(target=target, original=original, args=args, kwargs=kwargs)

    _sync_wrapper.__agentscope_wrapped__ = True  # type: ignore[attr-defined]
    return _sync_wrapper


def _resolve_parent(module: Any, path: tuple[str, ...]) -> tuple[Any, str] | None:
    if not path:
        return None

    parent = module
    for part in path[:-1]:
        parent = getattr(parent, part, None)
        if parent is None:
            return None
    return parent, path[-1]


def _patch_target(target: TargetSpec) -> None:
    if target.key in _PATCHED_TARGETS:
        return

    module = sys.modules.get(target.module)
    if module is None:
        return

    resolved = _resolve_parent(module, target.path)
    if resolved is None:
        return
    parent, attr_name = resolved
    current = getattr(parent, attr_name, None)
    if current is None:
        return
    if getattr(current, "__agentscope_wrapped__", False):
        _PATCHED_TARGETS.add(target.key)
        return

    if target.key not in _ORIGINALS:
        _ORIGINALS[target.key] = current
    setattr(parent, attr_name, _build_wrapper(_ORIGINALS[target.key], target))
    _PATCHED_TARGETS.add(target.key)


def _try_patch_available_targets() -> None:
    for target in _ACTIVE_TARGETS:
        _patch_target(target)


def _install_import_hook() -> None:
    global _IMPORT_HOOK_INSTALLED
    if _IMPORT_HOOK_INSTALLED:
        return

    def _instrumenting_import(
        name: str,
        globals_dict: dict[str, Any] | None = None,
        locals_dict: dict[str, Any] | None = None,
        fromlist: tuple[Any, ...] = (),
        level: int = 0,
    ) -> Any:
        module = _ORIGINAL_IMPORT(name, globals_dict, locals_dict, fromlist, level)
        _try_patch_available_targets()
        return module

    builtins.__import__ = _instrumenting_import
    _IMPORT_HOOK_INSTALLED = True


def _resolve_enabled_targets(providers: list[str] | None) -> list[TargetSpec]:
    if providers is None:
        enabled = {adapter.name for adapter in PROVIDER_REGISTRY}
    else:
        enabled = {name.lower() for name in providers}

    targets: list[TargetSpec] = []
    for adapter in PROVIDER_REGISTRY:
        if adapter.name in enabled:
            targets.extend(adapter.targets)
    return targets


def auto_instrument(providers: list[str] | None = None) -> None:
    global _ACTIVE_TARGETS
    _ACTIVE_TARGETS = _resolve_enabled_targets(providers)
    instrument_requests()
    _install_import_hook()
    _try_patch_available_targets()
