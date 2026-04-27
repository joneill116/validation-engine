"""
RuleResult — the outcome of executing one rule.

Captures execution status (PASSED/FAILED/ERROR/SKIPPED), counts, timing,
and the findings the rule produced. A rule failing to *execute* (an
exception) is distinct from a rule reporting a *data* failure.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .enums import RuleExecutionStatus, Scope
from .error import ValidationError
from .finding import ValidationFinding
from .observation import Observation


@dataclass(frozen=True)
class RuleResult:
    """
    The outcome of executing one rule against the request payload.

    Fields:
        rule_id: ID of the rule.
        rule_version: Version of the rule.
        status: How the execution finished.
        scope: Field/entity/collection scope.
        findings: Findings the rule produced (pass and fail).
        evaluated_count: Total findings emitted (``passed_count + failed_count``).
            For field-scope rules: one per (entity, matching field) evaluation.
            For entity-scope rules: at least one per entity evaluated.
            For collection-scope rules: one per group/result the rule emitted.
        passed_count: Number of findings with ``passed=True``.
        failed_count: Number of findings with ``passed=False``.
        duration_ms: Wall-clock execution time in milliseconds.
        error: Populated when status is ERROR.
    """

    rule_id: str
    rule_version: str
    status: RuleExecutionStatus
    scope: Scope
    findings: tuple[ValidationFinding, ...] = field(default_factory=tuple)
    observations: tuple[Observation, ...] = field(default_factory=tuple)
    evaluated_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    duration_ms: float = 0.0
    error: ValidationError | None = None
    # Optional rule-group membership echoed from the originating rule —
    # lets ValidationSummary aggregate failed findings by group_id.
    group_id: str | None = None
    skip_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.observations, tuple):
            object.__setattr__(self, "observations", tuple(self.observations))
        if not isinstance(self.findings, tuple):
            object.__setattr__(self, "findings", tuple(self.findings))
