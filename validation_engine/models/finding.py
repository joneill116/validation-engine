"""
ValidationFinding — evidence of a data-quality issue or pass observation.

A finding is *not* a runtime error. It records what the rule observed
about the data (pass or fail). Runtime/framework errors are represented
by ValidationError instead.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from ._immutable import freeze
from .enums import Severity, Category


@dataclass(frozen=True)
class ValidationFinding:
    """
    A single observation produced by a rule against an entity/field.

    Fields:
        finding_id: Stable identifier for this finding instance.
        rule_id: ID of the rule that produced the finding.
        rule_version: Version of the rule (for audit reproducibility).
        severity: How severe the issue is.
        category: Functional category of the rule.
        passed: True if the data satisfied the rule.
        message: Human-readable summary.
        entity_ref: Reference identifiers for the entity (id, natural keys, ...).
        field_path: Dot/slash path of the field (if scoped to a field).
        expected: Expected value/shape (for audit).
        actual: Actual value observed (for audit).
        evidence: Optional structured evidence (additional context, snippets).
        involved_fields: Other fields the rule consulted.
        metadata: Free-form key/value pairs.
    """

    rule_id: str
    severity: Severity
    category: Category
    passed: bool
    message: str
    finding_id: str = field(default_factory=lambda: f"f_{uuid.uuid4().hex[:12]}")
    rule_version: str = "1.0"
    entity_ref: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    field_path: str | None = None
    expected: Any = None
    actual: Any = None
    evidence: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    involved_fields: tuple[str, ...] = field(default_factory=tuple)
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.entity_ref, MappingProxyType):
            object.__setattr__(self, "entity_ref", freeze(self.entity_ref))
        if not isinstance(self.evidence, MappingProxyType):
            object.__setattr__(self, "evidence", freeze(self.evidence))
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))
        if not isinstance(self.involved_fields, tuple):
            object.__setattr__(self, "involved_fields", tuple(self.involved_fields))
