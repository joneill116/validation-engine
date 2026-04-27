"""
ValidationTarget — what a rule is being applied to.

Until now, "target" was implicit in a rule's ``scope``: a FIELD-scope rule
ran against a field value, an ENTITY-scope rule against an entity dict, a
COLLECTION-scope rule against the entire entity list. That is fine for the
classic rules, but it cannot express:

  - "this rule is checking the relationship between two fields"
  - "this rule is checking a property of a group of entities sharing a key"

``ValidationTarget`` makes the target explicit so findings, plans, and
manifests can describe *exactly* what was evaluated and what failed.
Existing FIELD/ENTITY/COLLECTION rules can still skip this type — the
engine will synthesize a target from their scope/field_path on demand.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from ._immutable import freeze
from .enums import Scope


@dataclass(frozen=True)
class ValidationTarget:
    """
    The thing a rule is being applied to.

    Fields:
        scope: FIELD / ENTITY / COLLECTION / GROUP / RELATIONSHIP.
        field_path: dotted field path for FIELD targets, or the canonical
            field whose value the rule is evaluating for ENTITY targets.
        group_by: tuple of dotted paths used to bucket entities for GROUP
            targets (e.g. ``("entity_ref.account_id",)``).
        relationship_fields: ordered tuple of field paths participating in
            a RELATIONSHIP target (e.g. ``("issue_date", "maturity_date")``).
        metadata: free-form annotations carried into findings and plans.
    """

    scope: Scope
    field_path: str | None = None
    group_by: tuple[str, ...] = field(default_factory=tuple)
    relationship_fields: tuple[str, ...] = field(default_factory=tuple)
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.group_by, tuple):
            object.__setattr__(self, "group_by", tuple(self.group_by))
        if not isinstance(self.relationship_fields, tuple):
            object.__setattr__(self, "relationship_fields", tuple(self.relationship_fields))
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))
        # Light validation so authoring mistakes surface early. The engine
        # never sees an inconsistent target this way.
        if self.scope is Scope.RELATIONSHIP and len(self.relationship_fields) < 2:
            raise ValueError(
                "ValidationTarget(scope=RELATIONSHIP) requires at least two relationship_fields"
            )
        if self.scope is Scope.GROUP and not self.group_by:
            raise ValueError(
                "ValidationTarget(scope=GROUP) requires at least one group_by path"
            )

    @classmethod
    def field(cls, field_path: str, **metadata: Any) -> "ValidationTarget":
        """Sugar: build a FIELD target."""
        return cls(scope=Scope.FIELD, field_path=field_path, metadata=metadata or {})

    @classmethod
    def entity(cls, **metadata: Any) -> "ValidationTarget":
        """Sugar: build an ENTITY target."""
        return cls(scope=Scope.ENTITY, metadata=metadata or {})

    @classmethod
    def collection(cls, **metadata: Any) -> "ValidationTarget":
        """Sugar: build a COLLECTION target."""
        return cls(scope=Scope.COLLECTION, metadata=metadata or {})

    @classmethod
    def relationship(cls, *fields: str, **metadata: Any) -> "ValidationTarget":
        """Sugar: build a RELATIONSHIP target across the supplied field paths."""
        return cls(
            scope=Scope.RELATIONSHIP,
            relationship_fields=tuple(fields),
            metadata=metadata or {},
        )

    @classmethod
    def group(cls, *group_by: str, **metadata: Any) -> "ValidationTarget":
        """Sugar: build a GROUP target keyed on the supplied dotted paths."""
        return cls(
            scope=Scope.GROUP,
            group_by=tuple(group_by),
            metadata=metadata or {},
        )
