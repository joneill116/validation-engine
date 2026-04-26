"""
ConditionalRequiredRule — entity-scope rule.

If a precondition (``when``) field matches a value/value-set, then a
target field must be present and non-null.

Example config (the field names are caller-chosen; the framework
attaches no meaning to them)::

    when_field: <some_field>
    when_in: [<value_a>, <value_b>]
    require: <other_field>
"""
from __future__ import annotations

from typing import Any

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope
from ...models.finding import ValidationFinding
from ..configured import ConfiguredRule
from ._helpers import extract_field


class ConditionalRequiredRule(ConfiguredRule):
    rule_type = "conditional_required"

    def __init__(self, rule_id: str, **kwargs) -> None:
        kwargs.setdefault("scope", Scope.ENTITY)
        kwargs.setdefault("category", Category.COMPLETENESS)
        super().__init__(rule_id, **kwargs)
        self.when_field: str = self.params.get("when_field")
        self.when_equals: Any = self.params.get("when_equals")
        when_in = self.params.get("when_in")
        self.when_in: tuple = tuple(when_in) if when_in is not None else ()
        self.require_field: str = self.params.get("require")

        if not self.when_field or not self.require_field:
            raise ValueError(
                f"ConditionalRequiredRule {rule_id!r}: 'when_field' and 'require' are required"
            )
        if self.when_equals is None and not self.when_in:
            raise ValueError(
                f"ConditionalRequiredRule {rule_id!r}: provide 'when_equals' or 'when_in'"
            )

    def _condition_matches(self, value: Any) -> bool:
        if self.when_in:
            return value in self.when_in
        return value == self.when_equals

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding:
        fields = target.get("fields", {}) if isinstance(target, dict) else {}
        when_value = extract_field(fields, self.when_field)
        if not self._condition_matches(when_value):
            return self.make_finding(
                passed=True,
                message=(
                    f"Conditional check vacuously satisfied "
                    f"({self.when_field}={when_value!r} did not match precondition)"
                ),
                involved_fields=(self.when_field, self.require_field),
                expected="precondition match",
                actual={self.when_field: when_value},
            )
        require_value = extract_field(fields, self.require_field)
        present = require_value is not None and require_value != ""
        return self.make_finding(
            passed=present,
            message=self._message(
                f"Field {self.require_field!r} is required when "
                f"{self.when_field}={when_value!r}"
            ) if not present else f"Conditional requirement satisfied",
            field_path=self.require_field,
            expected="<non-null>",
            actual=require_value,
            involved_fields=(self.when_field, self.require_field),
        )
