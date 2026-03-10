from __future__ import annotations

from typing import Any


def coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None

    return None


def normalize_usage(input_tokens: Any, output_tokens: Any) -> tuple[int | None, int | None, int | None]:
    normalized_input = coerce_int(input_tokens)
    normalized_output = coerce_int(output_tokens)

    if normalized_input is None and normalized_output is None:
        return None, None, None

    total_tokens = (normalized_input or 0) + (normalized_output or 0)
    return normalized_input, normalized_output, total_tokens
