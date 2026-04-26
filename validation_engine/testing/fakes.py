"""
Ready-made fakes for testing rules and strategies without real infrastructure.

Usage in tests:
    from validation_engine.testing import field_rule, entity_rule, collection_rule
"""
from typing import Any
from ..contracts.enums import Severity, Scope, Category
from ..contracts.findings import Finding
from ..engine.context import EvaluationContext
from ..rules.base import make_finding


class _SimpleFieldRule:
    def __init__(
        self,
        rule_id: str,
        field_path: str,
        severity: Severity,
        category: Category,
        applies_to: set[str],
        should_pass: bool,
        message: str,
    ) -> None:
        self.rule_id = rule_id
        self.scope = Scope.FIELD
        self.severity = severity
        self.category = category
        self.field_path = field_path
        self.applies_to = applies_to
        self._should_pass = should_pass
        self._message = message

    def evaluate(self, target: Any, ctx: EvaluationContext) -> Finding:
        return make_finding(self, self._should_pass, self._message,
                            field_path=self.field_path, actual=target)


class _SimpleEntityRule:
    def __init__(
        self,
        rule_id: str,
        severity: Severity,
        category: Category,
        applies_to: set[str],
        should_pass: bool,
        message: str,
    ) -> None:
        self.rule_id = rule_id
        self.scope = Scope.ENTITY
        self.severity = severity
        self.category = category
        self.field_path = "*"
        self.applies_to = applies_to
        self._should_pass = should_pass
        self._message = message

    def evaluate(self, target: Any, ctx: EvaluationContext) -> Finding:
        return make_finding(self, self._should_pass, self._message)


class _SimpleCollectionRule:
    def __init__(
        self,
        rule_id: str,
        severity: Severity,
        category: Category,
        applies_to: set[str],
        should_pass: bool,
        message: str,
    ) -> None:
        self.rule_id = rule_id
        self.scope = Scope.COLLECTION
        self.severity = severity
        self.category = category
        self.field_path = "*"
        self.applies_to = applies_to
        self._should_pass = should_pass
        self._message = message

    def evaluate(self, target: Any, ctx: EvaluationContext) -> Finding:
        return make_finding(self, self._should_pass, self._message)


def field_rule(
    rule_id: str = "test.field_rule",
    field_path: str = "*",
    severity: Severity = Severity.BLOCKING,
    category: Category = Category.STRUCTURAL,
    applies_to: set[str] | None = None,
    passes: bool = True,
    message: str = "field rule result",
) -> _SimpleFieldRule:
    return _SimpleFieldRule(rule_id, field_path, severity, category,
                            applies_to or {"*"}, passes, message)


def entity_rule(
    rule_id: str = "test.entity_rule",
    severity: Severity = Severity.BLOCKING,
    category: Category = Category.CONSISTENCY,
    applies_to: set[str] | None = None,
    passes: bool = True,
    message: str = "entity rule result",
) -> _SimpleEntityRule:
    return _SimpleEntityRule(rule_id, severity, category,
                             applies_to or {"*"}, passes, message)


def collection_rule(
    rule_id: str = "test.collection_rule",
    severity: Severity = Severity.BLOCKING,
    category: Category = Category.UNIQUENESS,
    applies_to: set[str] | None = None,
    passes: bool = True,
    message: str = "collection rule result",
) -> _SimpleCollectionRule:
    return _SimpleCollectionRule(rule_id, severity, category,
                                 applies_to or {"*"}, passes, message)
