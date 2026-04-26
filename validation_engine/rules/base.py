"""
Rule base class.

A Rule is a callable object the engine executes against a target. The
target shape depends on the rule's scope:

  - FIELD scope      -> target is the field value
  - ENTITY scope     -> target is the full entity dict
  - COLLECTION scope -> target is the list of entity dicts

Rules return either a single ``ValidationFinding`` or an iterable of
them. The engine wraps the rule's execution in a ``RuleResult``
capturing status, timing, and the findings produced.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable, Mapping

from ..core.context import EvaluationContext
from ..models.enums import Category, Scope, Severity
from ..models.finding import ValidationFinding


class Rule(ABC):
    """
    Abstract base class for rules.

    Subclasses set the class-level metadata (or pass it through
    ``__init__``) and implement ``evaluate``. Rules MUST be deterministic
    given (target, context) so audit trails are reproducible.

    Attributes:
        rule_id: Stable identifier (used for traceability).
        rule_version: Version of the rule (audit trail).
        scope: FIELD / ENTITY / COLLECTION.
        severity: Severity assigned to non-passing findings.
        category: Functional category.
        field_path: For FIELD-scope rules, the field this rule targets.
            Use ``"*"`` to match every field on the entity.
        applies_to: Entity types this rule covers. Use ``frozenset({"*"})``
            for all.
    """

    rule_id: str = "rule"
    rule_version: str = "1.0"
    scope: Scope = Scope.FIELD
    severity: Severity = Severity.BLOCKING
    category: Category = Category.STRUCTURAL
    field_path: str = "*"
    # frozenset prevents accidental sharing/mutation across subclasses.
    applies_to: frozenset[str] = frozenset({"*"})

    @abstractmethod
    def evaluate(
        self, target: Any, ctx: EvaluationContext
    ) -> ValidationFinding | Iterable[ValidationFinding]:
        """Evaluate the rule against ``target``."""

    # ------------------------------------------------------------------

    def make_finding(
        self,
        passed: bool,
        message: str,
        *,
        field_path: str | None = None,
        expected: Any = None,
        actual: Any = None,
        evidence: Mapping[str, Any] | None = None,
        involved_fields: Iterable[str] = (),
        entity_ref: Mapping[str, Any] | None = None,
        severity: Severity | None = None,
    ) -> ValidationFinding:
        """Convenience constructor for findings produced by this rule."""
        resolved_field_path = field_path
        if resolved_field_path is None and self.scope is Scope.FIELD and self.field_path != "*":
            resolved_field_path = self.field_path
        return ValidationFinding(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            severity=severity or self.severity,
            category=self.category,
            passed=passed,
            message=message,
            field_path=resolved_field_path,
            expected=expected,
            actual=actual,
            evidence=evidence,
            involved_fields=tuple(involved_fields),
            entity_ref=entity_ref,
        )
