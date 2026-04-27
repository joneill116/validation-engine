"""
RangeRule — asserts a numeric field is within [min, max].
"""
from __future__ import annotations

from numbers import Real
from typing import Any

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope
from ...models.finding import ValidationFinding
from ...models import finding_codes
from ..configured import ConfiguredRule


class RangeRule(ConfiguredRule):
    rule_type = "range"
    finding_code = finding_codes.VALUE_OUT_OF_RANGE

    def __init__(self, rule_id: str, **kwargs) -> None:
        kwargs.setdefault("scope", Scope.FIELD)
        kwargs.setdefault("category", Category.BUSINESS)
        super().__init__(rule_id, **kwargs)
        self.min: float | None = self.params.get("min")
        self.max: float | None = self.params.get("max")
        self.inclusive_min: bool = bool(self.params.get("inclusive_min", True))
        self.inclusive_max: bool = bool(self.params.get("inclusive_max", True))
        if self.min is None and self.max is None:
            raise ValueError(
                f"RangeRule {rule_id!r}: at least one of 'min' or 'max' must be set"
            )

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding:
        if not isinstance(target, Real) or isinstance(target, bool):
            return self.make_finding(
                passed=False,
                message=self._message(
                    f"Field {self.field_path!r} must be numeric, got {type(target).__name__}"
                ),
                    expected=f"numeric in range [{self.min}, {self.max}]",
                actual=target,
            )
        ok_min = True
        ok_max = True
        if self.min is not None:
            ok_min = target >= self.min if self.inclusive_min else target > self.min
        if self.max is not None:
            ok_max = target <= self.max if self.inclusive_max else target < self.max
        passed = ok_min and ok_max
        return self.make_finding(
            passed=passed,
            message=self._message(
                f"Value {target} not in range [{self.min}, {self.max}]"
            ) if not passed else f"Value {target} in range",
            expected={"min": self.min, "max": self.max},
            actual=target,
        )
