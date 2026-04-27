"""
ValidationSummary — aggregated counts and metrics from a validation run.

Computed from RuleResult and ValidationFinding instances.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping

from ._immutable import freeze
from .enums import BLOCKING_SEVERITIES, RuleExecutionStatus, Severity
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
            (status PASSED / FAILED / ERROR — not SKIPPED, not NOT_APPLICABLE).
        skipped_count: rule_results with status == SKIPPED.
        not_applicable_count: rule_results with status == NOT_APPLICABLE.
        error_count: rule_results with status == ERROR.

        by_severity / by_category / by_rule_id / by_finding_code /
        by_field_path / by_rule_group: counts of *failed* findings keyed
        by the named dimension. Useful for quick aggregation in
        dashboards and downstream consumers.
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
    not_applicable_count: int = 0

    by_severity: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    by_category: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    by_rule_id: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    by_finding_code: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    by_field_path: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    by_rule_group: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        # Each aggregation must end up as an immutable mapping so the
        # whole summary is safely shareable.
        for name in (
            "by_severity", "by_category", "by_rule_id",
            "by_finding_code", "by_field_path", "by_rule_group",
        ):
            v = getattr(self, name)
            if not isinstance(v, MappingProxyType):
                object.__setattr__(self, name, freeze(v))

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
        not_applicable = sum(
            1 for r in rule_results if r.status is RuleExecutionStatus.NOT_APPLICABLE
        )
        error_count = sum(1 for r in rule_results if r.status is RuleExecutionStatus.ERROR)
        # Skipped *and* not-applicable rules don't count as evaluated. They
        # had no chance to make a finding so they shouldn't appear in the
        # denominator of the run.
        total_rules_evaluated = len(rule_results) - skipped - not_applicable

        passed = sum(1 for f in findings if f.passed)
        failed = sum(1 for f in findings if not f.passed)
        warning = sum(
            1 for f in findings if not f.passed and f.severity == Severity.WARNING
        )
        blocking = sum(
            1 for f in findings
            if not f.passed and f.severity in BLOCKING_SEVERITIES
        )
        total_findings = len(findings)
        pass_rate = (passed / total_findings) if total_findings else 1.0

        # ---- by-dimension counts (failed findings only) ----
        # Group lookup needs the rule_results index — only the rule
        # carries group_id, findings echo rule_id alone.
        rule_group_by_id = {
            r.rule_id: getattr(r, "group_id", None) for r in rule_results
        }
        # rule_results don't currently store group_id (kept on the Rule
        # instance), so dashboards usually attribute groups via rule_id.
        # When a downstream caller wants to roll up per group, the group
        # info lives on the rules they passed in. We still expose an
        # empty by_rule_group here for forward compat.

        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}
        by_rule_id: dict[str, int] = {}
        by_finding_code: dict[str, int] = {}
        by_field_path: dict[str, int] = {}
        by_rule_group: dict[str, int] = {}
        for f in findings:
            if f.passed:
                continue
            by_severity[f.severity.value] = by_severity.get(f.severity.value, 0) + 1
            by_category[f.category.value] = by_category.get(f.category.value, 0) + 1
            by_rule_id[f.rule_id] = by_rule_id.get(f.rule_id, 0) + 1
            if f.finding_code:
                by_finding_code[f.finding_code] = by_finding_code.get(f.finding_code, 0) + 1
            if f.field_path:
                by_field_path[f.field_path] = by_field_path.get(f.field_path, 0) + 1
            grp = rule_group_by_id.get(f.rule_id)
            if grp:
                by_rule_group[grp] = by_rule_group.get(grp, 0) + 1

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
            not_applicable_count=not_applicable,
            by_severity=by_severity,
            by_category=by_category,
            by_rule_id=by_rule_id,
            by_finding_code=by_finding_code,
            by_field_path=by_field_path,
            by_rule_group=by_rule_group,
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
            "not_applicable_count": self.not_applicable_count,
            "pass_rate": self.pass_rate,
            "by_severity": dict(self.by_severity),
            "by_category": dict(self.by_category),
            "by_rule_id": dict(self.by_rule_id),
            "by_finding_code": dict(self.by_finding_code),
            "by_field_path": dict(self.by_field_path),
            "by_rule_group": dict(self.by_rule_group),
        }
