"""Internal helpers shared by standard rule implementations."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


def extract_field(fields: Mapping[str, Any], name: str) -> Any:
    """
    Read a field value from an entity's ``fields`` mapping.

    Supports two payload shapes:
        - ``{"field": value}``                 — plain value
        - ``{"field": {"value": value, ...}}`` — rich field with metadata
    """
    raw = fields.get(name)
    if isinstance(raw, dict) and "value" in raw:
        return raw["value"]
    return raw


def to_decimal(value: Any) -> Decimal | None:
    """
    Convert a payload value to ``Decimal``.

    Returns:
        ``None`` only when ``value is None`` (caller decides whether
        absent means "skip" or "error").

    Raises:
        ``ValueError`` for anything that isn't safely convertible —
        booleans (technically ``int`` subclass but never a meaningful
        amount), NaN/Infinity (which would poison sums and break
        tolerance comparisons), or strings/objects ``Decimal`` can't
        parse. Callers surface this as a failed finding rather than
        silently treating bad data as zero.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"boolean is not a valid amount: {value!r}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"cannot convert {value!r} to Decimal: {exc}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite amount is not a valid value: {value!r}")
    return result
