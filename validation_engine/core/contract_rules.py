"""
Synthesize ``Rule`` instances that enforce a ``ContractSnapshot``.

When a request supplies a ``ContractSnapshot``, the engine appends three
families of synthetic rules to the rule list before execution:

  - One ``_ContractRequiredFieldRule`` per ``required=True`` field.
  - One ``_ContractFieldTypeRule`` per typed field whose ``field_type``
    is not ``"any"``. The check tolerates absent fields (the required
    rule above is responsible for missing-key reporting); only present
    values are type-checked. ``nullable=False`` causes ``None`` to fail
    the type check.
  - One ``_ContractRequiredEntityRefKeyRule`` per required entity_ref key.

Synthetic rule_ids are stable strings so they appear deterministically in
``ValidationSummary`` and ``ValidationManifest`` ruleset hashes.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from ..models.contract_snapshot import ContractFieldSnapshot, ContractSnapshot
from ..models.enums import Category, Scope, Severity
from ..models.finding import ValidationFinding
from ..models import finding_codes
from ..rules.base import Rule
from .context import EvaluationContext
from . import paths


# --- type matching ---------------------------------------------------------

def _is_decimal_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            return False
        return True
    if isinstance(value, str):
        try:
            d = Decimal(value)
        except (InvalidOperation, ValueError):
            return False
        return d.is_finite()
    return False


def _matches(value: Any, expected: str) -> bool:
    if expected == "any":
        return True
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "decimal":
        return _is_decimal_like(value)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "date":
        return isinstance(value, date) and not isinstance(value, datetime)
    if expected == "datetime":
        return isinstance(value, datetime)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return False


# --- field lookup respecting the rich shape -------------------------------

_MISSING = object()


def _read_field(fields: Mapping[str, Any], field_path: str) -> Any:
    """Return the value at ``field_path`` from ``fields`` or ``_MISSING``."""
    head, _, tail = field_path.partition(".")
    raw = fields.get(head, _MISSING) if isinstance(fields, Mapping) else _MISSING
    if raw is _MISSING:
        return _MISSING
    if isinstance(raw, Mapping) and "value" in raw and not tail:
        return raw["value"]
    if not tail:
        return raw
    return paths.get_path(raw, tail, default=_MISSING)


# --- synthetic rule classes ------------------------------------------------

class _ContractRequiredFieldRule(Rule):
    """Synthetic ENTITY-scope rule: the field must be present per the contract."""

    scope = Scope.ENTITY
    severity = Severity.BLOCKING
    category = Category.STRUCTURAL
    finding_code = finding_codes.CONTRACT_FIELD_MISSING
    field_path = "*"
    applies_to = frozenset({"*"})

    def __init__(self, contract_id: str, field: ContractFieldSnapshot) -> None:
        self.rule_id = f"_contract.{contract_id}.{field.field_path}.required"
        self._field_path = field.field_path
        self._nullable = field.nullable

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding:
        fields = target.get("fields", {}) if isinstance(target, dict) else {}
        raw = _read_field(fields, self._field_path)
        # Missing key fails. Present-but-None passes the required check
        # only when the contract allows nullable; otherwise we treat None
        # as missing for the purpose of presence.
        present = raw is not _MISSING and (self._nullable or raw is not None)
        return self.make_finding(
            passed=present,
            message=(
                f"Required field {self._field_path!r} missing per contract"
                if not present else
                f"Required field {self._field_path!r} present"
            ),
            field_path=self._field_path,
            expected="<present>" if self._nullable else "<present and non-null>",
            actual=("<missing>" if raw is _MISSING else raw),
        )


class _ContractFieldTypeRule(Rule):
    """Synthetic ENTITY-scope rule: a present field must match the contract's type."""

    scope = Scope.ENTITY
    severity = Severity.BLOCKING
    category = Category.TYPE
    finding_code = finding_codes.CONTRACT_TYPE_MISMATCH
    field_path = "*"
    applies_to = frozenset({"*"})

    def __init__(self, contract_id: str, field: ContractFieldSnapshot) -> None:
        self.rule_id = f"_contract.{contract_id}.{field.field_path}.type"
        self._field_path = field.field_path
        self._field_type = field.field_type
        self._nullable = field.nullable

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding | None:
        fields = target.get("fields", {}) if isinstance(target, dict) else {}
        raw = _read_field(fields, self._field_path)
        if raw is _MISSING:
            # Missing-key reporting is the required-rule's job. Returning
            # None means "no finding" (the executor accepts that shape).
            return None
        if raw is None:
            # ``nullable=True`` means None is acceptable for any type.
            ok = self._nullable
            return self.make_finding(
                passed=ok,
                message=(
                    f"Field {self._field_path!r} is null but contract marks "
                    f"it non-nullable"
                ) if not ok else f"Field {self._field_path!r} null (allowed)",
                field_path=self._field_path,
                expected=self._field_type,
                actual=None,
            )
        ok = _matches(raw, self._field_type)
        return self.make_finding(
            passed=ok,
            message=(
                f"Field {self._field_path!r} expected type {self._field_type}, "
                f"got {type(raw).__name__}"
            ) if not ok else f"Field {self._field_path!r} type matches",
            field_path=self._field_path,
            expected=self._field_type,
            actual=raw,
        )


class _ContractRequiredEntityRefKeyRule(Rule):
    """Synthetic ENTITY-scope rule: the entity_ref must carry a required key."""

    scope = Scope.ENTITY
    severity = Severity.BLOCKING
    category = Category.STRUCTURAL
    finding_code = finding_codes.CONTRACT_FIELD_MISSING
    field_path = "*"
    applies_to = frozenset({"*"})

    def __init__(self, contract_id: str, key: str) -> None:
        self.rule_id = f"_contract.{contract_id}.entity_ref.{key}.required"
        self._key = key

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding:
        ref = target.get("entity_ref", {}) if isinstance(target, dict) else {}
        present = self._key in (ref or {})
        return self.make_finding(
            passed=present,
            message=(
                f"Required entity_ref key {self._key!r} missing per contract"
                if not present else
                f"Required entity_ref key {self._key!r} present"
            ),
            expected=f"entity_ref.{self._key}",
            actual="<missing>" if not present else "<present>",
        )


# --- public synthesizer ----------------------------------------------------

def synthesize_contract_rules(snapshot: ContractSnapshot) -> list[Rule]:
    """
    Build the list of synthetic rules that enforce ``snapshot``.

    The returned rules use the same ``Rule`` interface as user rules, so
    they go through the executor unchanged. Their ``rule_id`` strings
    start with ``_contract.`` to make them easy to filter in summary
    aggregations.
    """
    out: list[Rule] = []
    for fld in snapshot.fields:
        if fld.required:
            out.append(_ContractRequiredFieldRule(snapshot.contract_id, fld))
        if fld.field_type != "any":
            out.append(_ContractFieldTypeRule(snapshot.contract_id, fld))
    for key in snapshot.required_entity_ref_keys:
        out.append(_ContractRequiredEntityRefKeyRule(snapshot.contract_id, key))
    return out
