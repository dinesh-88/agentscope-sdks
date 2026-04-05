from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..run import _current_run_state, observe_run
from .propagation import TraceContext, extract_from_asgi_headers, extract_from_mapping, inject_into_metadata

_STARLETTE_PATCHED = False
_GRPC_SERVER_PATCHED = False
_CELERY_PATCHED = False
_KAFKA_PYTHON_PATCHED = False


def instrument_orchestration(
    *,
    workflow_name: str = "orchestration_auto_trace",
    agent_name: str = "orchestrator",
    transports: bool | str | Iterable[str] = "auto",
) -> None:
    selected = _resolve_transports(transports)
    if "http" in selected:
        _instrument_starlette(
            workflow_name=workflow_name,
            agent_name=agent_name,
        )
    if "grpc" in selected:
        _instrument_grpc(
            workflow_name=workflow_name,
            agent_name=agent_name,
        )
    if "celery" in selected:
        _instrument_celery(
            workflow_name=workflow_name,
            agent_name=agent_name,
        )
    if "kafka" in selected:
        _instrument_kafka_python(
            workflow_name=workflow_name,
            agent_name=agent_name,
        )


def _resolve_transports(raw: bool | str | Iterable[str]) -> set[str]:
    all_transports = {"http", "grpc", "celery", "kafka"}
    if raw is True or raw == "auto":
        return all_transports
    if raw is False:
        return set()
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"all", "*"}:
            return all_transports
        if not normalized:
            return set()
        return {normalized}
    selected: set[str] = set()
    for item in raw:
        normalized = str(item).strip().lower()
        if normalized:
            selected.add(normalized)
    return selected


def _instrument_starlette(*, workflow_name: str, agent_name: str) -> None:
    global _STARLETTE_PATCHED
    if _STARLETTE_PATCHED:
        return

    try:
        from starlette.applications import Starlette
    except Exception:
        return

    current = Starlette.__call__
    if getattr(current, "__agentscope_wrapped__", False):
        _STARLETTE_PATCHED = True
        return

    async def wrapped_call(self: Any, scope: dict[str, Any], receive: Any, send: Any) -> Any:
        if str(scope.get("type", "")).lower() != "http":
            return await current(self, scope, receive, send)

        if _current_run_state() is not None:
            return await current(self, scope, receive, send)

        inbound = extract_from_asgi_headers(scope.get("headers"))
        metadata = _build_asgi_metadata(scope)
        with observe_run(
            workflow_name,
            agent_name=agent_name,
            trace_id=inbound.trace_id,
            parent_run_id=inbound.parent_run_id,
            root_run_id=inbound.root_run_id,
            metadata=metadata,
            session_id=metadata.get("request_id"),
        ):
            return await current(self, scope, receive, send)

    wrapped_call.__agentscope_wrapped__ = True  # type: ignore[attr-defined]
    Starlette.__call__ = wrapped_call  # type: ignore[assignment]
    _STARLETTE_PATCHED = True


def _instrument_grpc(*, workflow_name: str, agent_name: str) -> None:
    global _GRPC_SERVER_PATCHED

    try:
        import grpc
    except Exception:
        return

    if not _GRPC_SERVER_PATCHED:
        current_server = grpc.server
        if not getattr(current_server, "__agentscope_wrapped__", False):

            def wrapped_server(*args: Any, **kwargs: Any) -> Any:
                interceptors = list(kwargs.get("interceptors") or [])
                has_agentscope = any(
                    getattr(interceptor, "__class__", type(interceptor)).__name__ == "_AgentScopeGrpcServerInterceptor"
                    for interceptor in interceptors
                )
                if not has_agentscope:
                    interceptors.append(
                        _AgentScopeGrpcServerInterceptor(
                            workflow_name=workflow_name,
                            agent_name=agent_name,
                        )
                    )
                kwargs["interceptors"] = tuple(interceptors)
                return current_server(*args, **kwargs)

            wrapped_server.__agentscope_wrapped__ = True  # type: ignore[attr-defined]
            grpc.server = wrapped_server  # type: ignore[assignment]
        _GRPC_SERVER_PATCHED = True


def _instrument_celery(*, workflow_name: str, agent_name: str) -> None:
    global _CELERY_PATCHED
    if _CELERY_PATCHED:
        return

    try:
        from celery.app.task import Task
    except Exception:
        return

    current = Task.__call__
    if getattr(current, "__agentscope_wrapped__", False):
        _CELERY_PATCHED = True
        return

    def wrapped_task_call(self: Any, *args: Any, **kwargs: Any) -> Any:
        if _current_run_state() is not None:
            return current(self, *args, **kwargs)

        request = getattr(self, "request", None)
        request_headers = getattr(request, "headers", None)
        inbound = extract_from_mapping(request_headers if isinstance(request_headers, dict) else None)
        task_id = str(getattr(request, "id", "") or "")
        metadata = {
            "auto_orchestration": True,
            "transport": "celery",
            "task_name": getattr(self, "name", None),
            "task_id": task_id or None,
        }

        with observe_run(
            workflow_name,
            agent_name=agent_name,
            trace_id=inbound.trace_id,
            parent_run_id=inbound.parent_run_id,
            root_run_id=inbound.root_run_id,
            metadata=metadata,
            session_id=task_id or None,
        ):
            return current(self, *args, **kwargs)

    wrapped_task_call.__agentscope_wrapped__ = True  # type: ignore[attr-defined]
    Task.__call__ = wrapped_task_call  # type: ignore[assignment]
    _CELERY_PATCHED = True


def _instrument_kafka_python(*, workflow_name: str, agent_name: str) -> None:
    global _KAFKA_PYTHON_PATCHED
    if _KAFKA_PYTHON_PATCHED:
        return

    try:
        from kafka import KafkaConsumer, KafkaProducer  # type: ignore
    except Exception:
        return

    current_consumer_poll = KafkaConsumer.poll
    if not getattr(current_consumer_poll, "__agentscope_wrapped__", False):

        def wrapped_consumer_poll(self: Any, *args: Any, **kwargs: Any) -> Any:
            active = getattr(self, "_agentscope_active_run_cm", None)
            if active is not None:
                active.__exit__(None, None, None)
                setattr(self, "_agentscope_active_run_cm", None)

            records_by_topic = current_consumer_poll(self, *args, **kwargs)
            if _current_run_state() is not None:
                return records_by_topic
            if not records_by_topic:
                return records_by_topic

            first_record = None
            for records in records_by_topic.values():
                if records:
                    first_record = records[0]
                    break
            if first_record is None:
                return records_by_topic

            inbound = extract_from_mapping(_headers_to_mapping(getattr(first_record, "headers", None)))
            metadata = {
                "auto_orchestration": True,
                "transport": "kafka",
                "topic": getattr(first_record, "topic", None),
                "partition": getattr(first_record, "partition", None),
                "offset": getattr(first_record, "offset", None),
            }
            cm = observe_run(
                workflow_name,
                agent_name=agent_name,
                trace_id=inbound.trace_id,
                parent_run_id=inbound.parent_run_id,
                root_run_id=inbound.root_run_id,
                metadata=metadata,
            )
            cm.__enter__()
            setattr(self, "_agentscope_active_run_cm", cm)
            return records_by_topic

        wrapped_consumer_poll.__agentscope_wrapped__ = True  # type: ignore[attr-defined]
        KafkaConsumer.poll = wrapped_consumer_poll  # type: ignore[assignment]

    current_producer_send = KafkaProducer.send
    if not getattr(current_producer_send, "__agentscope_wrapped__", False):

        def wrapped_producer_send(self: Any, topic: str, value: Any = None, key: Any = None, headers: Any = None, *args: Any, **kwargs: Any) -> Any:
            next_headers = list(headers or [])
            header_mapping = _headers_to_mapping(next_headers)
            injected = inject_into_metadata(list(header_mapping.items()))
            next_headers = [(k, v.encode("utf-8")) for k, v in injected]
            return current_producer_send(self, topic, value=value, key=key, headers=next_headers, *args, **kwargs)

        wrapped_producer_send.__agentscope_wrapped__ = True  # type: ignore[attr-defined]
        KafkaProducer.send = wrapped_producer_send  # type: ignore[assignment]

    _KAFKA_PYTHON_PATCHED = True


def _build_asgi_metadata(scope: dict[str, Any]) -> dict[str, Any]:
    headers: dict[str, str] = {}
    for raw_key, raw_value in scope.get("headers") or []:
        try:
            key = raw_key.decode("latin-1").lower()
            value = raw_value.decode("latin-1")
        except Exception:
            continue
        headers[key] = value

    client = scope.get("client") or ()
    client_host = None
    if isinstance(client, tuple) and len(client) > 0:
        client_host = client[0]

    request_id = (
        headers.get("x-request-id")
        or headers.get("x-correlation-id")
        or headers.get("traceparent")
    )

    return {
        "auto_orchestration": True,
        "transport": "http",
        "framework": "starlette",
        "method": scope.get("method"),
        "path": scope.get("path"),
        "query_string": _decode_query_string(scope.get("query_string")),
        "client_ip": client_host,
        "request_id": request_id,
    }


def _decode_query_string(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            return raw.decode("utf-8")
        except Exception:
            return None
    if isinstance(raw, str):
        return raw
    return None


def _headers_to_mapping(raw_headers: Any) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in raw_headers or []:
        if not isinstance(item, tuple) or len(item) != 2:
            continue
        key, value = item
        try:
            normalized_key = str(key).lower()
            if isinstance(value, bytes):
                normalized_value = value.decode("utf-8")
            else:
                normalized_value = str(value)
        except Exception:
            continue
        mapping[normalized_key] = normalized_value
    return mapping


class _AgentScopeGrpcServerInterceptor:
    def __init__(self, *, workflow_name: str, agent_name: str) -> None:
        self.workflow_name = workflow_name
        self.agent_name = agent_name

    def intercept_service(self, continuation: Any, handler_call_details: Any) -> Any:
        handler = continuation(handler_call_details)
        if handler is None:
            return None

        inbound = extract_from_mapping(dict(handler_call_details.invocation_metadata or []))

        def _run_with_context(fn: Any, request_or_iterator: Any, context: Any) -> Any:
            if _current_run_state() is not None:
                return fn(request_or_iterator, context)
            metadata = {
                "auto_orchestration": True,
                "transport": "grpc",
                "method": getattr(handler_call_details, "method", None),
            }
            with observe_run(
                self.workflow_name,
                agent_name=self.agent_name,
                trace_id=inbound.trace_id,
                parent_run_id=inbound.parent_run_id,
                root_run_id=inbound.root_run_id,
                metadata=metadata,
            ):
                return fn(request_or_iterator, context)

        if getattr(handler, "unary_unary", None) is not None:
            return _grpc().unary_unary_rpc_method_handler(
                lambda req, ctx: _run_with_context(handler.unary_unary, req, ctx),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if getattr(handler, "unary_stream", None) is not None:
            return _grpc().unary_stream_rpc_method_handler(
                lambda req, ctx: _run_with_context(handler.unary_stream, req, ctx),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if getattr(handler, "stream_unary", None) is not None:
            return _grpc().stream_unary_rpc_method_handler(
                lambda req, ctx: _run_with_context(handler.stream_unary, req, ctx),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if getattr(handler, "stream_stream", None) is not None:
            return _grpc().stream_stream_rpc_method_handler(
                lambda req, ctx: _run_with_context(handler.stream_stream, req, ctx),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        return handler


def _grpc() -> Any:
    import grpc

    return grpc

