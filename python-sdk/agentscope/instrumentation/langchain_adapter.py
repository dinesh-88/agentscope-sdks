from __future__ import annotations

import inspect
from typing import Any, Callable

from .registry import ProviderAdapter, TargetSpec
from .token_usage import coerce_int, normalize_usage


def _safe_getattr(value: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(value, name, default)
    except Exception:
        return default


def _extract_call_data(
    original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
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


def _safe_get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return _safe_getattr(value, key, default)


def _extract_text(response: Any) -> str | None:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        content = response.get("content")
        if isinstance(content, str):
            return content
        text = response.get("text")
        if isinstance(text, str):
            return text
        return None
    content = _safe_getattr(response, "content")
    if isinstance(content, str):
        return content
    text = _safe_getattr(response, "text")
    if isinstance(text, str):
        return text
    return None


def _extract_usage(response: Any) -> tuple[int | None, int | None, int | None]:
    usage_metadata = _safe_get(response, "usage_metadata")
    response_metadata = _safe_get(response, "response_metadata")
    token_usage = _safe_get(response_metadata, "token_usage")

    input_tokens = _safe_get(usage_metadata, "input_tokens")
    if input_tokens is None:
        input_tokens = _safe_get(token_usage, "input_tokens")
    if input_tokens is None:
        input_tokens = _safe_get(token_usage, "prompt_tokens")

    output_tokens = _safe_get(usage_metadata, "output_tokens")
    if output_tokens is None:
        output_tokens = _safe_get(token_usage, "output_tokens")
    if output_tokens is None:
        output_tokens = _safe_get(token_usage, "completion_tokens")

    total_tokens = _safe_get(usage_metadata, "total_tokens")
    if total_tokens is None:
        total_tokens = _safe_get(token_usage, "total_tokens")

    input_tokens, output_tokens, normalized_total = normalize_usage(input_tokens, output_tokens)
    parsed_total = coerce_int(total_tokens)
    if parsed_total is None:
        parsed_total = normalized_total

    return input_tokens, output_tokens, parsed_total


def _request_extractor(
    original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    data = _extract_call_data(original, args, kwargs)
    llm_obj = data.get("self")
    model = _safe_getattr(llm_obj, "model_name") or _safe_getattr(llm_obj, "model")
    input_data = data.get("input") or data.get("messages") or data.get("prompt")
    return {
        "model": model,
        "messages": input_data if isinstance(input_data, list) else None,
        "prompt": input_data if isinstance(input_data, (str, dict)) else None,
    }


def _response_extractor(response: Any) -> dict[str, Any]:
    input_tokens, output_tokens, total_tokens = _extract_usage(response)
    return {
        "response_text": _extract_text(response),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def get_adapter() -> ProviderAdapter:
    return ProviderAdapter(
        name="langchain",
        targets=(
            TargetSpec(
                key="langchain.chat.invoke",
                provider="langchain",
                module="langchain_core.language_models.chat_models",
                path=("BaseChatModel", "invoke"),
                request_extractor=_request_extractor,
                response_extractor=_response_extractor,
            ),
            TargetSpec(
                key="langchain.chat.ainvoke",
                provider="langchain",
                module="langchain_core.language_models.chat_models",
                path=("BaseChatModel", "ainvoke"),
                request_extractor=_request_extractor,
                response_extractor=_response_extractor,
            ),
            TargetSpec(
                key="langchain.llm.invoke",
                provider="langchain",
                module="langchain_core.language_models.llms",
                path=("BaseLLM", "invoke"),
                request_extractor=_request_extractor,
                response_extractor=_response_extractor,
            ),
            TargetSpec(
                key="langchain.llm.ainvoke",
                provider="langchain",
                module="langchain_core.language_models.llms",
                path=("BaseLLM", "ainvoke"),
                request_extractor=_request_extractor,
                response_extractor=_response_extractor,
            ),
        ),
    )
