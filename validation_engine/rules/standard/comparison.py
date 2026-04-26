"""
ComparisonRule — entity-scope rule comparing two field values.

Supported operators: ``eq``, ``ne``, ``gt``, ``gte``, ``lt``, ``lte``.
"""
from __future__ import annotations

from typing import Any

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope
from ...models.finding import ValidationFinding
from ..configured import ConfiguredRule
from ._helpers import extract_field

_OPERATORS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
}


class ComparisonRule(ConfiguredRule):
    rule_type = "comparison"

    def __init__(self, rule_id: str, **kwargs) -> None:
        kwargs.setdefault("scope", Scope.ENTITY)
        kwargs.setdefault("category", Category.CONSISTENCY)
        super().__init__(rule_id, **kwargs)
        self.left: str = self.params.get("left")
        self.right: str = self.params.get("right")
        self.operator: str = self.params.get("operator", "eq")
        if not self.left or not self.right:
            raise ValueError(
                f"ComparisonRule {rule_id!r}: 'left' and 'right' field names are required"
            )
        op_fn = _OPERATORS.get(self.operator)
        if op_fn is None:
            raise ValueError(
                f"ComparisonRule {rule_id!r}: unsupported operator {self.operator!r}; "
                f"valid: {sorted(_OPERATORS)}"
            )
        self._op = op_fn

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding:
        fields = target.get("fields", {}) if isinstance(target, dict) else {}
        left_val = extract_field(fields, self.left)
        right_val = extract_field(fields, self.right)
        try:
            passed = self._op(left_val, right_val)
        except TypeError as exc:
            return self.make_finding(
                passed=False,
                message=self._message(
                    f"Cannot compare {self.left}({left_val!r}) {self.operator} "
                    f"{self.right}({right_val!r}): {exc}"
                ),
                expected=f"{self.left} {self.operator} {self.right}",
                actual={self.left: left_val, self.right: right_val},
                involved_fields=(self.left, self.right),
            )
        return self.make_finding(
            passed=passed,
            message=self._message(
                f"Expected {self.left} {self.operator} {self.right}, "
                f"got {left_val!r} vs {right_val!r}"
            ) if not passed else f"{self.left} {self.operator} {self.right} satisfied",
            expected=f"{self.left} {self.operator} {self.right}",
            actual={self.left: left_val, self.right: right_val},
            involved_fields=(self.left, self.right),
        )
