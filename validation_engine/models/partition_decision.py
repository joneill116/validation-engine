"""
PartitionDecision — one decision for a slice of the validation run.

A partition is any *dimension* of the dataset chosen by the caller:
per record, per group key, per field path, or any tuple combination.
The strategy applies its decision logic to each partition independently.
The framework is dimension-agnostic — the caller names the keys.

The framework still exposes a single run-level ``ValidationDecision``
on ``ValidationResult.decision`` for the orchestration signal. The
per-slice routing lives on ``ValidationResult.partition_decisions``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .decision import ValidationDecision


@dataclass(frozen=True)
class PartitionDecision:
    """
    The decision for one partition of a validation run.

    Fields:
        dimension: Human-readable description of the partition axis
            chosen by the caller, e.g. ``"entity_ref.<your_key>"`` or a
            tuple form like ``"(entity_ref.<key_a>, fields.<key_b>)"``.
        key: The partition key, always a tuple. Single-key partitions
            use a 1-tuple; multi-key partitions concatenate components.
            Components are whatever the partition function returned
            (typically primitive values).
        decision: The routing decision for this partition.
        entity_count: Number of entities in this partition.
        finding_count: Number of findings produced for this partition.
        failed_count: Number of findings with ``passed=False``.
    """

    dimension: str
    key: tuple[Any, ...]
    decision: ValidationDecision
    entity_count: int = 0
    finding_count: int = 0
    failed_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.key, tuple):
            object.__setattr__(self, "key", tuple(self.key))

    @property
    def action(self):
        return self.decision.action

    @property
    def target(self) -> str | None:
        return self.decision.target

    @property
    def publish_allowed(self) -> bool:
        return self.decision.publish_allowed
