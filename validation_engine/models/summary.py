"""
ValidationSummary — aggregated counts and metrics from a validation run.

Computed from RuleResult and ValidationFinding instances.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .enums import RuleExecutionStatus, Severity
from .finding import ValidationFinding
from .rule_result import RuleResult


@dataclass(frozen=True)
class ValidationSummary:
    """
    Aggregated metrics for a validation run.

    Use ``ValidationSummary.from_results()`` to derive this object from
    rule results and findings; do not construct by hand.

    Field semantics:
        total_rules_evaluated: rule_results whose rule actually executed
            (status != SKIPPED).
        skipped_count: rule_results with status == SKIPPED.
        error_count: rule_results with status == ERROR.
    """

    total_rules_evaluated: int
    total_entities_evaluated: int
    total_findings: int
    passed_count: int
    failed_count: int
    warning_count: int
    blocking_count: int
    error_count: int
    skipped_count: int
    pass_rate: float

    @classmethod
    def from_results(
        cls,
        rule_results: Iterable[RuleResult],
        findings: Iterable[ValidationFinding],
        total_entities_evaluated: int,
    ) -> "ValidationSummary":
        rule_results = tuple(rule_results)
        findings = tuple(findings)

        skipped = sum(1 for r in rule_results if r.status is RuleExecutionStatus.SKIPPED)
        error_count = sum(1 for r in rule_results if r.status is RuleExecutionStatus.ERROR)
        total_rules_evaluated = len(rule_results) - skipped

        passed = sum(1 for f in findings if f.passed)
        failed = sum(1 for f in findings if not f.passed)
        warning = sum(
            1 for f in findings if not f.passed and f.severity == Severity.WARNING
        )
        blocking = sum(
            1 for f in findings
            if not f.passed and f.severity in (Severity.BLOCKING, Severity.FATAL)
        )
        total_findings = len(findings)
        pass_rate = (passed / total_findings) if total_findings else 1.0

        return cls(
            total_rules_evaluated=total_rules_evaluated,
            total_entities_evaluated=total_entities_evaluated,
            total_findings=total_findings,
            passed_count=passed,
            failed_count=failed,
            warning_count=warning,
            blocking_count=blocking,
            error_count=error_count,
            skipped_count=skipped,
            pass_rate=round(pass_rate, 4),
        )

    def as_dict(self) -> dict:
        return {
            "total_rules_evaluated": self.total_rules_evaluated,
            "total_entities_evaluated": self.total_entities_evaluated,
            "total_findings": self.total_findings,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "warning_count": self.warning_count,
            "blocking_count": self.blocking_count,
            "error_count": self.error_count,
            "skipped_count": self.skipped_count,
            "pass_rate": self.pass_rate,
        }
