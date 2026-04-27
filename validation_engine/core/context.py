"""
EvaluationContext — first-class context handed to every rule.

Provides rules access to the originating ``ValidationRequest``, the
current entity / field path, the active ruleset metadata, and reference
data. Rules pull what they need from this context rather than having
dependencies injected on a per-rule basis.

Tenant / source / processing metadata lives on ``ctx.request.metadata``.

The context now exposes:
  - ``target``: the explicit ``ValidationTarget`` for this evaluation
  - ``field_value`` / ``entity_ref``: shorthand handles for FIELD-/ENTITY-
    scope rules so they don't need to dig through ``current_entity``
  - ``get_field`` / ``has_field``: dotted-path lookups against
    ``current_entity['fields']``
  - ``get_ref`` / ``get_reference_data``: helpers around the two
    ambient lookup tables (entity_ref + reference data snapshots)

Existing rules that only consult ``request`` / ``current_entity`` /
``current_field_path`` / ``reference_data`` continue to work unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Mapping, TYPE_CHECKING

from ..models._immutable import freeze
from ..models.target import ValidationTarget
from . import paths

if TYPE_CHECKING:
    from ..models.request import ValidationRequest


_MISSING = object()


@dataclass(frozen=True)
class EvaluationContext:
    """
    Immutable context handed to every ``rule.evaluate(target, ctx)`` call.

    Fields:
        request: The originating ValidationRequest.
        ruleset_id: Active ruleset identifier (echoed from request).
        ruleset_version: Active ruleset version (echoed from request).
        rule_id: Identifier of the rule currently executing.
        target: Optional explicit ValidationTarget for this evaluation.
        current_entity: Current entity dict (ENTITY/FIELD scope only).
        current_field_path: Field path under evaluation (FIELD scope only).
        field_value: The raw field value being evaluated (FIELD scope only).
        entity_ref: Convenience handle to ``current_entity['entity_ref']``.
        reference_data: Lookup tables for rules to consult (allowed
            values, validity windows, etc.) — caller-supplied content.
    """

    request: "ValidationRequest"
    ruleset_id: str
    ruleset_version: str
    rule_id: str | None = None
    target: ValidationTarget | None = None
    current_entity: Mapping[str, Any] | None = None
    current_field_path: str | None = None
    field_value: Any = None
    entity_ref: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    reference_data: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.reference_data, MappingProxyType):
            object.__setattr__(self, "reference_data", freeze(self.reference_data))
        if not isinstance(self.entity_ref, MappingProxyType):
            object.__setattr__(self, "entity_ref", freeze(self.entity_ref))

    # ------------------------------------------------------------------
    # mutation helpers
    # ------------------------------------------------------------------

    def scoped(
        self,
        *,
        rule_id: str | None = None,
        entity: Mapping[str, Any] | None = None,
        field_path: str | None = None,
        target: ValidationTarget | None = None,
        field_value: Any = _MISSING,
        entity_ref: Mapping[str, Any] | None = None,
    ) -> "EvaluationContext":
        """Return a copy with the supplied fields stamped in one pass."""
        changes: dict[str, Any] = {}
        if rule_id is not None:
            changes["rule_id"] = rule_id
        if entity is not None:
            changes["current_entity"] = entity
            if entity_ref is None:
                # If the caller didn't pin the ref explicitly, derive it.
                ref = entity.get("entity_ref") if isinstance(entity, Mapping) else None
                if ref is not None:
                    changes["entity_ref"] = freeze(ref)
        if field_path is not None:
            changes["current_field_path"] = field_path
        if target is not None:
            changes["target"] = target
        if field_value is not _MISSING:
            changes["field_value"] = field_value
        if entity_ref is not None:
            changes["entity_ref"] = freeze(entity_ref)
        return replace(self, **changes) if changes else self

    # ------------------------------------------------------------------
    # accessor helpers (read-only)
    # ------------------------------------------------------------------

    def get_field(self, field_path: str, default: Any = None) -> Any:
        """
        Return the value at ``field_path`` from ``current_entity['fields']``.

        Supports dotted paths into nested mappings. The legacy "rich"
        single-level shape (``{"value": x, ...}``) is unwrapped on the
        first segment so older payloads keep working.
        """
        if self.current_entity is None:
            return default
        fields = self.current_entity.get("fields") if isinstance(self.current_entity, Mapping) else None
        if fields is None:
            return default
        head, _, tail = field_path.partition(".")
        raw = fields.get(head, _MISSING) if isinstance(fields, Mapping) else _MISSING
        if raw is _MISSING:
            return default
        if isinstance(raw, Mapping) and "value" in raw and not tail:
            return raw["value"]
        if not tail:
            return raw
        return paths.get_path(raw, tail, default=default)

    def has_field(self, field_path: str) -> bool:
        """Return True if ``field_path`` resolves on ``current_entity``."""
        return self.get_field(field_path, default=_MISSING) is not _MISSING

    def get_ref(self, key: str, default: Any = None) -> Any:
        """Return a value from ``entity_ref`` (supports dotted paths)."""
        if not self.entity_ref:
            return default
        if "." not in key:
            return self.entity_ref.get(key, default)
        return paths.get_path(dict(self.entity_ref), key, default=default)

    def get_reference_data(self, name: str, default: Any = None) -> Any:
        """Return imported reference data by name."""
        if not self.reference_data:
            return default
        if "." not in name:
            return self.reference_data.get(name, default)
        return paths.get_path(dict(self.reference_data), name, default=default)

    def get_threshold_policy(self, policy_id: str) -> Any:
        """
        Return the named ``ThresholdPolicy`` from ``request.profile``, or None.

        Rules that opt into threshold-based severity (e.g. SumEqualsRule
        with ``threshold_policy: <id>``) call this to resolve the
        configured policy. Returns ``None`` when no profile is attached
        to the request or the policy_id isn't registered.
        """
        profile = getattr(self.request, "profile", None)
        if profile is None:
            return None
        return profile.get_threshold_policy(policy_id)
