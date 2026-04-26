"""
RequiredRule — assert a key is present on the entity.

Distinct from ``NotNullRule`` which asserts the *value* is not
None/empty. Pass the field name via ``field_path``.
"""
from __future__ import annotations

from typing import Any

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope
from ...models.finding import ValidationFinding
from ..configured import ConfiguredRule


class RequiredRule(ConfiguredRule):
    rule_type = "required"

    def __init__(self, rule_id: str, **kwargs) -> None:
        kwargs.setdefault("scope", Scope.ENTITY)
        kwargs.setdefault("category", Category.COMPLETENESS)
        super().__init__(rule_id, **kwargs)
        if not self.field_path or self.field_path == "*":
            raise ValueError(
                f"RequiredRule {rule_id!r}: 'field_path' must name the required field"
            )

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding:
        fields = target.get("fields", {}) if isinstance(target, dict) else {}
        present = self.field_path in fields
        return self.make_finding(
            passed=present,
            message=self._message(
                f"Field {self.field_path!r} is required but missing"
            ) if not present else f"Field {self.field_path!r} present",
            field_path=self.field_path,
            expected="<present>",
            actual="<missing>" if not present else "<present>",
        )
