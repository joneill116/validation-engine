"""
TypeCheckRule — assert a field's value is of the expected logical type.

Logical types are intentionally narrow: ``string``, ``integer``, ``decimal``,
``boolean``, ``date``, ``datetime``, ``object``, ``array``, ``any``. The
rule does not coerce — it asserts. Strings that *look like* a date are
*not* treated as dates here (use ``regex`` or ``date_between`` for that).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from numbers import Real
from typing import Any

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope
from ...models.finding import ValidationFinding
from ...models import finding_codes
from ..configured import ConfiguredRule


_VALID_TYPES = frozenset({
    "string", "integer", "decimal", "boolean",
    "date", "datetime", "object", "array", "any",
})


def _is_decimal_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, (int, float)):
        # Reject NaN/Inf — they would silently corrupt downstream maths.
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            return False
        return True
    if isinstance(value, str):
        try:
            d = Decimal(value)
        except (InvalidOperation, ValueError):
            return False
        return d.is_finite()
    return False


def _matches(value: Any, expected: str) -> bool:
    if expected == "any":
        return True
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        # bool is technically int — exclude it because a bool is not a count.
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "decimal":
        return _is_decimal_like(value)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "date":
        return isinstance(value, date) and not isinstance(value, datetime)
    if expected == "datetime":
        return isinstance(value, datetime)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return False


class TypeCheckRule(ConfiguredRule):
    rule_type = "type_check"
    finding_code = finding_codes.INVALID_TYPE

    def __init__(self, rule_id: str, **kwargs) -> None:
        kwargs.setdefault("scope", Scope.FIELD)
        kwargs.setdefault("category", Category.TYPE)
        super().__init__(rule_id, **kwargs)
        expected = self.params.get("expected_type")
        if expected not in _VALID_TYPES:
            raise ValueError(
                f"TypeCheckRule {rule_id!r}: 'expected_type' must be one of "
                f"{sorted(_VALID_TYPES)}, got {expected!r}"
            )
        self.expected_type: str = expected

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding:
        ok = _matches(target, self.expected_type)
        return self.make_finding(
            passed=ok,
            message=self._message(
                f"Field {self.field_path!r} expected type {self.expected_type}, "
                f"got {type(target).__name__}"
            ) if not ok else f"Field {self.field_path!r} matches type {self.expected_type}",
            expected=self.expected_type,
            actual=target,
        )
