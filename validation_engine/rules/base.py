"""
Rule base class.

A Rule is a callable object the engine executes against a target. The
target shape depends on the rule's scope:

  - FIELD scope      -> target is the field value
  - ENTITY scope     -> target is the full entity dict
  - COLLECTION scope -> target is the list of entity dicts

Rules return either a single ``ValidationFinding``, an iterable of them,
or a ``RuleEvaluation``. The engine wraps the rule's execution in a
``RuleResult`` capturing status, timing, and the findings produced.

Two rule-author styles are supported:

1. Classic positional API ("legacy"): ``evaluate(target, ctx) -> Finding | Iterable[Finding]``.
   Existing rules and most domain extensions use this. It still works.
2. Context-only API: ``evaluate(ctx) -> RuleEvaluation``. Cleaner for
   rules that need to emit observations or report ``NOT_APPLICABLE``.
   The executor detects this style by signature inspection and routes
   accordingly. New standard rules opt into helpers like ``self.passed()``
   and ``self.failed_finding()`` that produce the right shapes.
"""
from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any, Iterable, Mapping

from ..core.context import EvaluationContext
from ..models.applicability import RuleApplicability
from ..models.dependency import RuleDependency
from ..models.enums import Category, RuleEvaluationStatus, Scope, Severity
from ..models.finding import ValidationFinding
from ..models.observation import Observation
from ..models.rule_evaluation import RuleEvaluation
from ..models.target import ValidationTarget


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
        finding_code: Default machine-readable code for failed findings
            produced by this rule. Subclasses override; empty by default.
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
    finding_code: str = ""
    field_path: str = "*"
    # frozenset prevents accidental sharing/mutation across subclasses.
    applies_to: frozenset[str] = frozenset({"*"})
    # New (Phase 4) attributes — gating + sequencing + group membership.
    # Defaults are non-restrictive: empty applicability means "always
    # applicable", empty dependencies means "no prerequisites".
    applies_when: RuleApplicability = RuleApplicability()
    depends_on: tuple[RuleDependency, ...] = ()
    group_id: str | None = None

    @abstractmethod
    def evaluate(
        self, *args: Any, **kwargs: Any
    ) -> ValidationFinding | Iterable[ValidationFinding] | RuleEvaluation:
        """
        Evaluate the rule.

        Two signatures are recognized by the executor:

        - ``evaluate(self, target, ctx)`` (legacy, positional)
        - ``evaluate(self, ctx)``         (context-only)

        Either form may return a single ``ValidationFinding``, an iterable
        of them, or a ``RuleEvaluation``. The engine normalizes whichever
        form the rule emits.
        """

    # ------------------------------------------------------------------
    # finding helpers
    # ------------------------------------------------------------------

    def make_finding(
        self,
        passed: bool,
        message: str,
        *,
        finding_code: str | None = None,
        field_path: str | None = None,
        expected: Any = None,
        actual: Any = None,
        evidence: Mapping[str, Any] | None = None,
        involved_fields: Iterable[str] = (),
        entity_ref: Mapping[str, Any] | None = None,
        severity: Severity | None = None,
        target: ValidationTarget | None = None,
        observation_ids: Iterable[str] = (),
    ) -> ValidationFinding:
        """Convenience constructor for findings produced by this rule."""
        resolved_field_path = field_path
        if resolved_field_path is None and self.scope is Scope.FIELD and self.field_path != "*":
            resolved_field_path = self.field_path
        # ``finding_code`` is a per-call override over the class default.
        # Passing the empty string explicitly clears the code, which is
        # rarely what callers want — that's why an explicit None falls
        # back to the class attribute.
        code = finding_code if finding_code is not None else self.finding_code
        # Pass-findings carry no failure code by definition; clearing it
        # avoids polluting dashboards with codes attached to PASSED rows.
        if passed and finding_code is None:
            code = ""
        return ValidationFinding(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            severity=severity or self.severity,
            category=self.category,
            passed=passed,
            message=message,
            finding_code=code,
            target=target,
            field_path=resolved_field_path,
            expected=expected,
            actual=actual,
            evidence=evidence,
            involved_fields=tuple(involved_fields),
            entity_ref=entity_ref,
            observation_ids=tuple(observation_ids),
        )

    # ------------------------------------------------------------------
    # RuleEvaluation helpers (new API)
    # ------------------------------------------------------------------

    def passed(self, *, observations: Iterable[Observation] = ()) -> RuleEvaluation:
        """Build a passing ``RuleEvaluation``."""
        return RuleEvaluation.passed(observations=observations)

    def failed(
        self,
        findings: ValidationFinding | Iterable[ValidationFinding],
        *,
        observations: Iterable[Observation] = (),
    ) -> RuleEvaluation:
        """Build a failing ``RuleEvaluation`` from one or many findings."""
        if isinstance(findings, ValidationFinding):
            findings = (findings,)
        return RuleEvaluation.failed(findings=findings, observations=observations)

    def not_applicable(self, reason: str | None = None) -> RuleEvaluation:
        """Build a ``NOT_APPLICABLE`` evaluation."""
        return RuleEvaluation.not_applicable(reason)

    def observation(
        self,
        metric_name: str,
        value: Any,
        *,
        unit: str | None = None,
        field_path: str | None = None,
        dimensions: Mapping[str, Any] | None = None,
        evidence: Mapping[str, Any] | None = None,
        entity_ref: Mapping[str, Any] | None = None,
    ) -> Observation:
        """Convenience constructor for an ``Observation`` from this rule."""
        return Observation(
            rule_id=self.rule_id,
            metric_name=metric_name,
            value=value,
            unit=unit,
            field_path=field_path,
            dimensions=dimensions or {},
            evidence=evidence or {},
            entity_ref=entity_ref or {},
        )

    # ------------------------------------------------------------------
    # signature introspection
    # ------------------------------------------------------------------

    @classmethod
    def _evaluate_takes_target(cls) -> bool:
        """
        True iff ``evaluate`` accepts the legacy ``(target, ctx)`` form.

        Used by the executor to decide how to dispatch the call. We cache
        the result on the class to avoid paying for ``inspect.signature``
        on every rule evaluation.
        """
        cached = cls.__dict__.get("__evaluate_takes_target__")
        if cached is not None:
            return cached
        try:
            sig = inspect.signature(cls.evaluate)
        except (TypeError, ValueError):
            takes_target = True  # safest default
        else:
            params = [
                p for p in sig.parameters.values()
                if p.name != "self"
                and p.kind in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
            takes_target = len(params) >= 2
        setattr(cls, "__evaluate_takes_target__", takes_target)
        return takes_target
