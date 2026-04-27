"""
RuleEvaluation — the structured return value from a rule's ``evaluate``.

Older rules return ``ValidationFinding | Iterable[ValidationFinding]``.
That works but loses information: a passing rule may want to record an
observation, an inapplicable rule has no finding to emit, and a rule that
ran might want to attach metadata about *how* it ran. ``RuleEvaluation``
makes those cases explicit while still being trivial to construct via the
``passed`` / ``failed`` / ``not_applicable`` factories.

Existing rules can keep their current return type — the engine adapts at
the executor boundary (Phase 3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable

from ._immutable import freeze
from .enums import RuleEvaluationStatus
from .finding import ValidationFinding
from .observation import Observation


@dataclass(frozen=True)
class RuleEvaluation:
    """
    The structured outcome of evaluating one rule against one target.

    Use the ``passed``/``failed``/``not_applicable`` classmethods rather
    than constructing directly — they keep the (status, findings) pair
    consistent.
    """

    status: RuleEvaluationStatus
    findings: tuple[ValidationFinding, ...] = field(default_factory=tuple)
    observations: tuple[Observation, ...] = field(default_factory=tuple)
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.findings, tuple):
            object.__setattr__(self, "findings", tuple(self.findings))
        if not isinstance(self.observations, tuple):
            object.__setattr__(self, "observations", tuple(self.observations))
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))

    # -- factory methods ------------------------------------------------

    @classmethod
    def passed(
        cls,
        observations: Iterable[Observation] = (),
    ) -> "RuleEvaluation":
        return cls(
            status=RuleEvaluationStatus.PASSED,
            observations=tuple(observations),
        )

    @classmethod
    def failed(
        cls,
        findings: Iterable[ValidationFinding],
        observations: Iterable[Observation] = (),
    ) -> "RuleEvaluation":
        findings_t = tuple(findings)
        if not findings_t:
            raise ValueError(
                "RuleEvaluation.failed() requires at least one finding"
            )
        return cls(
            status=RuleEvaluationStatus.FAILED,
            findings=findings_t,
            observations=tuple(observations),
        )

    @classmethod
    def not_applicable(cls, reason: str | None = None) -> "RuleEvaluation":
        return cls(
            status=RuleEvaluationStatus.NOT_APPLICABLE,
            metadata={"reason": reason} if reason else {},
        )
