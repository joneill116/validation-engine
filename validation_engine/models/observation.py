"""
Observation — a measured fact recorded during validation.

Findings answer "what failed and why". Observations answer "what did the
rule actually measure?" — counts, ratios, totals, durations, distances.
A passing rule may emit observations; a failing rule's findings will
typically reference one or more observation IDs as their evidence.

The split lets downstream consumers (dashboards, alerting, regression
analysis) reason about *trends* in the observed metrics independently of
whether the rule happened to pass on a given run.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any

from ._immutable import freeze


@dataclass(frozen=True)
class Observation:
    """
    A measured fact emitted by a rule (independent of pass/fail).

    Fields:
        observation_id: Stable instance ID for cross-referencing from
            findings (``finding.observation_ids``).
        rule_id: ID of the rule that produced the observation.
        metric_name: Domain-neutral name of the measured metric
            (``record_count``, ``completeness_ratio``, ``sum_difference``).
        value: The measured value. Strings, numbers, decimals, dates, and
            JSON-friendly mappings are supported.
        unit: Optional unit string (``"records"``, ``"USD"``, ``"%"``).
        entity_ref: Reference to the entity the observation pertains to
            (empty for collection-/group-scope observations).
        field_path: Field path the observation pertains to (when relevant).
        dimensions: Free-form dimension labels (e.g. ``{"group": "A"}``).
        observed_at: When the observation was made (UTC).
        evidence: Structured supporting evidence (sample rows, breakdowns).
        metadata: Free-form context.
    """

    rule_id: str
    metric_name: str
    value: Any

    # Full 32-char UUID hex (see ValidationFinding for rationale).
    observation_id: str = field(default_factory=lambda: f"obs_{uuid.uuid4().hex}")
    unit: str | None = None
    entity_ref: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    field_path: str | None = None
    dimensions: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    observed_at: datetime | None = None
    evidence: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.entity_ref, MappingProxyType):
            object.__setattr__(self, "entity_ref", freeze(self.entity_ref))
        if not isinstance(self.dimensions, MappingProxyType):
            object.__setattr__(self, "dimensions", freeze(self.dimensions))
        if not isinstance(self.evidence, MappingProxyType):
            object.__setattr__(self, "evidence", freeze(self.evidence))
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))
