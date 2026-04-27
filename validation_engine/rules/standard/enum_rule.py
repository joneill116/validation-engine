"""
EnumRule — asserts the field value is in an allowed set.
"""
from __future__ import annotations

from typing import Any

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope
from ...models.finding import ValidationFinding
from ...models import finding_codes
from ..configured import ConfiguredRule


class EnumRule(ConfiguredRule):
    rule_type = "enum"
    finding_code = finding_codes.VALUE_NOT_ALLOWED

    def __init__(self, rule_id: str, **kwargs) -> None:
        kwargs.setdefault("scope", Scope.FIELD)
        kwargs.setdefault("category", Category.STRUCTURAL)
        super().__init__(rule_id, **kwargs)
        values = self.params.get("values")
        if not values:
            raise ValueError(
                f"EnumRule {rule_id!r}: 'values' parameter (list) is required"
            )
        self.allowed: tuple = tuple(values)
        self.case_sensitive: bool = bool(self.params.get("case_sensitive", True))
        # Pre-compute lookup set so evaluate() is allocation-free.
        self._lookup: frozenset = frozenset(
            self.allowed if self.case_sensitive
            else (v.lower() if isinstance(v, str) else v for v in self.allowed)
        )

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding:
        probe = (
            target.lower() if (not self.case_sensitive and isinstance(target, str))
            else target
        )
        passed = probe in self._lookup
        return self.make_finding(
            passed=passed,
            message=self._message(
                f"{target!r} is not one of {list(self.allowed)}"
            ) if not passed else f"{target!r} is allowed",
            expected=list(self.allowed),
            actual=target,
        )
