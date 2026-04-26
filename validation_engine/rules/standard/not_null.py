"""
NotNullRule — asserts the field value is non-null and (by default) non-empty.
"""
from __future__ import annotations

from typing import Any

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope
from ...models.finding import ValidationFinding
from ..configured import ConfiguredRule


def _is_blank(value: Any, allow_empty: bool) -> bool:
    if value is None:
        return True
    if allow_empty:
        return False
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


class NotNullRule(ConfiguredRule):
    rule_type = "not_null"

    def __init__(self, rule_id: str, **kwargs) -> None:
        kwargs.setdefault("scope", Scope.FIELD)
        kwargs.setdefault("category", Category.COMPLETENESS)
        super().__init__(rule_id, **kwargs)
        self.allow_empty: bool = bool(self.params.get("allow_empty", False))

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding:
        is_blank = _is_blank(target, self.allow_empty)
        return self.make_finding(
            passed=not is_blank,
            message=self._message(
                f"Field {self.field_path!r} must not be null/empty"
            ) if is_blank else f"Field {self.field_path!r} has value",
            expected="<non-null>",
            actual=target,
        )
