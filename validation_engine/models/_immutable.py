"""Internal helpers for the model layer."""
from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping


def freeze(value: Mapping[str, Any] | None) -> MappingProxyType:
    """Return ``value`` as an immutable mapping view, or empty for None/falsy."""
    return MappingProxyType(dict(value)) if value else MappingProxyType({})
