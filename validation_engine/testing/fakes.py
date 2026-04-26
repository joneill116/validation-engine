"""
Lightweight test rules.

Usage::

    from validation_engine.testing import field_rule, entity_rule
    rule = field_rule(passes=True)
"""
from __future__ import annotations

from typing import Any, Iterable

from ..core.context import EvaluationContext
from ..models.enums import Category, Scope, Severity
from ..models.finding import ValidationFinding
from ..rules.base import Rule


class _SimpleFieldRule(Rule):
    def __init__(
        self, rule_id: str, field_path: str, severity: Severity,
        category: Category, applies_to: Iterable[str], passes: bool, message: str,
    ) -> None:
        self.rule_id = rule_id
        self.scope = Scope.FIELD
        self.severity = severity
        self.category = category
        self.field_path = field_path
        self.applies_to = frozenset(applies_to)
        self._passes = passes
        self._message = message

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding:
        return self.make_finding(
            passed=self._passes, message=self._message, actual=target,
        )


class _SimpleEntityRule(Rule):
    def __init__(
        self, rule_id: str, severity: Severity, category: Category,
        applies_to: Iterable[str], passes: bool, message: str,
    ) -> None:
        self.rule_id = rule_id
        self.scope = Scope.ENTITY
        self.severity = severity
        self.category = category
        self.field_path = "*"
        self.applies_to = frozenset(applies_to)
        self._passes = passes
        self._message = message

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding:
        return self.make_finding(passed=self._passes, message=self._message)


def field_rule(
    rule_id: str = "test.field_rule",
    field_path: str = "*",
    severity: Severity = Severity.BLOCKING,
    category: Category = Category.STRUCTURAL,
    applies_to: Iterable[str] | None = None,
    passes: bool = True,
    message: str = "field rule result",
) -> _SimpleFieldRule:
    return _SimpleFieldRule(
        rule_id, field_path, severity, category, applies_to or {"*"}, passes, message,
    )


def entity_rule(
    rule_id: str = "test.entity_rule",
    severity: Severity = Severity.BLOCKING,
    category: Category = Category.CONSISTENCY,
    applies_to: Iterable[str] | None = None,
    passes: bool = True,
    message: str = "entity rule result",
) -> _SimpleEntityRule:
    return _SimpleEntityRule(
        rule_id, severity, category, applies_to or {"*"}, passes, message,
    )
