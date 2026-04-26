"""
Strategy protocols.

A ``PublishStrategy`` turns the run-level signals (findings, errors,
summary) into a single ``ValidationDecision``. It does not know about
queues, topics, or any downstream destination — it produces a *logical*
target identifier and lets the caller bind that to infrastructure.

A ``PerPartitionStrategy`` additionally produces one decision per
partition of the dataset, where a partition is any user-chosen
dimension (per record, per group key, per field, or any tuple thereof).
``PartitionedStrategy`` is the canonical implementation; any custom
strategy can opt in by implementing ``decide_per_partition``.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from ..models.decision import ValidationDecision
from ..models.error import ValidationError
from ..models.finding import ValidationFinding
from ..models.partition_decision import PartitionDecision
from ..models.summary import ValidationSummary


@runtime_checkable
class PublishStrategy(Protocol):
    strategy_id: str

    def decide(
        self,
        findings: Iterable[ValidationFinding],
        errors: Iterable[ValidationError],
        summary: ValidationSummary,
    ) -> ValidationDecision: ...


@runtime_checkable
class PerPartitionStrategy(Protocol):
    """
    Optional protocol — strategies that produce per-partition decisions.

    The engine calls ``decide()`` for the run-level decision and, if
    ``isinstance(strategy, PerPartitionStrategy)`` is true, also calls
    ``decide_per_partition()`` to populate
    ``ValidationResult.partition_decisions``.
    """

    strategy_id: str

    def decide_per_partition(
        self,
        findings: Iterable[ValidationFinding],
        errors: Iterable[ValidationError],
        summary: ValidationSummary,
        entities: tuple[Mapping[str, Any], ...],
    ) -> tuple[PartitionDecision, ...]: ...
