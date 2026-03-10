from __future__ import annotations

import inspect
from typing import Any, Callable

from .registry import ProviderAdapter, TargetSpec


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
    return {
        "response_text": _extract_text(response),
        "input_tokens": None,
        "output_tokens": None,
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
