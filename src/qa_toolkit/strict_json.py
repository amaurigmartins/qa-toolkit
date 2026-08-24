"""Strict JSON decoding shared by durable and external state boundaries."""

from __future__ import annotations

import json
from typing import Any, cast


def require_json_object(value: object, label: str) -> dict[str, Any]:
    """Return one string-keyed JSON object or reject the boundary value."""
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise RuntimeError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def require_json_array(value: object, label: str) -> list[object]:
    """Return one JSON array or reject the boundary value."""
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be an array")
    return cast(list[object], value)


def require_json_string(value: object, label: str) -> str:
    """Return one non-empty JSON string or reject the boundary value."""
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{label} must be a non-empty string")
    return value


def require_json_boolean(value: object, label: str) -> bool:
    """Return one JSON boolean or reject the boundary value."""
    if not isinstance(value, bool):
        raise RuntimeError(f"{label} must be a boolean")
    return value


def strict_json_loads(content: str | bytes) -> object:
    """Decode JSON while rejecting duplicate keys and non-standard constants."""
    return json.loads(
        content,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant: {value}")
