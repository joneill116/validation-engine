"""
ValidationPlan — preview what a run will do without executing it.

A plan is the engine's answer to "what would you do for this request?":
which rules will run, which are disabled, what targets are evaluated,
which dependencies exist, which reference data is required.

Plans are produced by ``ValidationEngine.plan(request)``. They are
serializable so they can be persisted and diffed.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from ._immutable import freeze


@dataclass(frozen=True)
class PlannedRule:
    rule_id: str
    rule_version: str
    rule_type: str
    scope: str
    severity: str
    category: str
    field_path: str | None = None
    group_id: str | None = None
    enabled: bool = True
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    has_applicability: bool = False
    skip_reason: str | None = None
    target: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.dependencies, tuple):
            object.__setattr__(self, "dependencies", tuple(self.dependencies))
        if not isinstance(self.target, MappingProxyType):
            object.__setattr__(self, "target", freeze(self.target))


@dataclass(frozen=True)
class ValidationPlan:
    plan_id: str
    request_id: str | None
    ruleset_id: str
    ruleset_version: str | None
    profile_id: str | None = None
    profile_version: str | None = None
    contract_id: str | None = None
    contract_version: str | None = None
    planned_rules: tuple[PlannedRule, ...] = field(default_factory=tuple)
    required_reference_data: tuple[str, ...] = field(default_factory=tuple)
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.planned_rules, tuple):
            object.__setattr__(self, "planned_rules", tuple(self.planned_rules))
        if not isinstance(self.required_reference_data, tuple):
            object.__setattr__(self, "required_reference_data", tuple(self.required_reference_data))
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))


def make_plan_id() -> str:
    return f"plan_{uuid.uuid4().hex[:12]}"
