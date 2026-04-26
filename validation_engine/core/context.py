"""
EvaluationContext — first-class context handed to every rule.

Provides rules access to the originating ``ValidationRequest``, the
current entity / field path, the active ruleset metadata, and reference
data. Rules pull what they need from this context rather than having
dependencies injected on a per-rule basis.

Tenant / source / processing metadata lives on ``ctx.request.metadata``.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Mapping, TYPE_CHECKING

from ..models._immutable import freeze

if TYPE_CHECKING:
    from ..models.request import ValidationRequest


@dataclass(frozen=True)
class EvaluationContext:
    """
    Immutable context handed to every ``rule.evaluate(target, ctx)`` call.

    Fields:
        request: The originating ValidationRequest.
        ruleset_id: Active ruleset identifier (echoed from request).
        ruleset_version: Active ruleset version (echoed from request).
        rule_id: Identifier of the rule currently executing.
        current_entity: Current entity dict (ENTITY/FIELD scope only).
        current_field_path: Field path under evaluation (FIELD scope only).
        reference_data: Lookup tables for rules to consult (allowed
            values, validity windows, etc.) — caller-supplied content.
    """

    request: "ValidationRequest"
    ruleset_id: str
    ruleset_version: str
    rule_id: str | None = None
    current_entity: Mapping[str, Any] | None = None
    current_field_path: str | None = None
    reference_data: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.reference_data, MappingProxyType):
            object.__setattr__(self, "reference_data", freeze(self.reference_data))

    def scoped(
        self,
        *,
        rule_id: str | None = None,
        entity: Mapping[str, Any] | None = None,
        field_path: str | None = None,
    ) -> "EvaluationContext":
        """Return a copy with rule/entity/field stamped in one pass."""
        changes: dict[str, Any] = {}
        if rule_id is not None:
            changes["rule_id"] = rule_id
        if entity is not None:
            changes["current_entity"] = entity
        if field_path is not None:
            changes["current_field_path"] = field_path
        return replace(self, **changes) if changes else self
