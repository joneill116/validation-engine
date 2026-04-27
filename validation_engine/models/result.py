"""
ValidationResult — full container for one validation run.

Carries findings, rule results, errors, summary, decision, and the
originating request id together so the run is fully auditable from a
single object.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType

from ._immutable import freeze
from .decision import ValidationDecision
from .enums import ValidationStatus
from .error import ValidationError
from .finding import ValidationFinding
from .manifest import ValidationManifest
from .observation import Observation
from .outcome import ValidationOutcome
from .partition_decision import PartitionDecision
from .rule_result import RuleResult
from .summary import ValidationSummary


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ValidationResult:
    """
    The full output of one validation run.

    Fields:
        validation_run_id: Unique identifier for the run.
        request_id: Echo of ValidationRequest.request_id.
        status: Overall outcome (PASSED / PASSED_WITH_WARNINGS / FAILED / ERROR).
        summary: Aggregated counts and metrics.
        decision: Run-level decision derived from findings/errors.
        partition_decisions: Per-partition decisions when the strategy
            supports per-partition routing (per record, per group key,
            per field, or any tuple combination chosen by the caller).
            Empty when the strategy is run-level only.
        findings: All findings emitted during the run.
        rule_results: One RuleResult per rule executed.
        errors: Runtime / framework errors (NOT data-quality findings).
        started_at, completed_at, duration_ms: Timing of the run.
        metadata: Free-form extra context.
    """

    validation_run_id: str
    request_id: str
    status: ValidationStatus
    summary: ValidationSummary
    decision: ValidationDecision
    findings: tuple[ValidationFinding, ...] = field(default_factory=tuple)
    rule_results: tuple[RuleResult, ...] = field(default_factory=tuple)
    errors: tuple[ValidationError, ...] = field(default_factory=tuple)
    partition_decisions: tuple[PartitionDecision, ...] = field(default_factory=tuple)
    observations: tuple[Observation, ...] = field(default_factory=tuple)
    # ``outcome`` is the validation-only verdict (introduced alongside the
    # operational ``decision``). Optional during the transition so older
    # callers / tests that build ValidationResult by hand continue to work.
    outcome: ValidationOutcome | None = None
    manifest: ValidationManifest | None = None
    started_at: datetime = field(default_factory=_utc_now)
    completed_at: datetime = field(default_factory=_utc_now)
    duration_ms: float = 0.0
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))
        if not isinstance(self.observations, tuple):
            object.__setattr__(self, "observations", tuple(self.observations))

    def failed_findings(self) -> tuple[ValidationFinding, ...]:
        """Convenience filter — used by reporting and exception flows."""
        return tuple(f for f in self.findings if not f.passed)
