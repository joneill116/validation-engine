"""
RuleApplicability — predicates that decide whether a rule should run.

Without applicability, every conditional check requires Python: "this
rule only applies when ``instrument_type`` is ``bond``" becomes a
hand-written rule. ``RuleApplicability`` lets that condition live in
configuration.

When the predicate evaluates false for a target, the engine records the
rule as ``NOT_APPLICABLE`` rather than ``PASSED`` — the distinction is
load-bearing for completeness reporting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from ._immutable import freeze


_MISSING = object()


class PredicateOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"


# Predicate operators that don't read ``value`` (presence checks).
_PRESENCE_OPS = frozenset({
    PredicateOperator.EXISTS,
    PredicateOperator.NOT_EXISTS,
    PredicateOperator.IS_NULL,
    PredicateOperator.IS_NOT_NULL,
})


@dataclass(frozen=True)
class ApplicabilityPredicate:
    """
    A single (field_path, operator, value) predicate.

    Non-presence operators ignore ``value`` — supplying it is harmless but
    not used. ``IN`` / ``NOT_IN`` accept a list/tuple/set.
    """

    field_path: str
    operator: PredicateOperator
    value: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.field_path, str) or not self.field_path:
            raise ValueError("ApplicabilityPredicate.field_path must be a non-empty string")
        if not isinstance(self.operator, PredicateOperator):
            object.__setattr__(self, "operator", PredicateOperator(self.operator))
        if self.operator in (PredicateOperator.IN, PredicateOperator.NOT_IN):
            if self.value is None:
                raise ValueError(
                    f"ApplicabilityPredicate({self.operator.value}) requires 'value' to be a collection"
                )
            if not isinstance(self.value, (list, tuple, set, frozenset)):
                raise ValueError(
                    f"ApplicabilityPredicate({self.operator.value}) value must be a list/tuple/set"
                )
            object.__setattr__(self, "value", tuple(self.value))


@dataclass(frozen=True)
class RuleApplicability:
    """
    A composable predicate group: ``match`` is ``"all"`` (default) or ``"any"``.

    An empty predicate list is treated as "always applicable" — the engine
    short-circuits the whole evaluation in that case.
    """

    predicates: tuple[ApplicabilityPredicate, ...] = field(default_factory=tuple)
    match: str = "all"
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.predicates, tuple):
            object.__setattr__(self, "predicates", tuple(self.predicates))
        if self.match not in ("all", "any"):
            raise ValueError(
                f"RuleApplicability.match must be 'all' or 'any', got {self.match!r}"
            )
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))

    @property
    def is_unconditional(self) -> bool:
        return not self.predicates

    def evaluate(self, fields: Mapping[str, Any]) -> bool:
        """Return True iff the rule should run against the supplied entity fields."""
        if self.is_unconditional:
            return True
        results: list[bool] = [_eval_predicate(p, fields) for p in self.predicates]
        if self.match == "any":
            return any(results)
        return all(results)


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------

def _eval_predicate(p: ApplicabilityPredicate, fields: Mapping[str, Any]) -> bool:
    from ..core.paths import get_path  # local import to dodge any future cycle

    raw = get_path(fields, p.field_path, default=_MISSING)
    # Support the legacy "rich field" shape on the head segment so
    # applicability behaves identically to ``ctx.get_field``.
    if (
        raw is not _MISSING
        and isinstance(raw, Mapping)
        and "value" in raw
        and "." not in p.field_path
    ):
        raw = raw["value"]
    op = p.operator
    if op is PredicateOperator.EXISTS:
        return raw is not _MISSING
    if op is PredicateOperator.NOT_EXISTS:
        return raw is _MISSING
    if op is PredicateOperator.IS_NULL:
        return raw is None or raw is _MISSING
    if op is PredicateOperator.IS_NOT_NULL:
        return raw is not None and raw is not _MISSING
    if raw is _MISSING:
        # Comparison/membership on a missing field => predicate is false.
        # That keeps the "this rule applies only when X is ..." reading
        # natural without surprising callers with TypeError.
        return False
    if op is PredicateOperator.EQUALS:
        return raw == p.value
    if op is PredicateOperator.NOT_EQUALS:
        return raw != p.value
    if op is PredicateOperator.IN:
        return raw in p.value
    if op is PredicateOperator.NOT_IN:
        return raw not in p.value
    try:
        if op is PredicateOperator.GREATER_THAN:
            return raw > p.value
        if op is PredicateOperator.GREATER_THAN_OR_EQUAL:
            return raw >= p.value
        if op is PredicateOperator.LESS_THAN:
            return raw < p.value
        if op is PredicateOperator.LESS_THAN_OR_EQUAL:
            return raw <= p.value
    except TypeError:
        # Heterogeneous comparison (e.g. string vs int) -> predicate false.
        return False
    raise ValueError(f"unsupported predicate operator: {op!r}")


def predicates_from_iterable(items: Iterable[Mapping[str, Any]]) -> tuple[ApplicabilityPredicate, ...]:
    """Helper used by the config loader to convert raw dicts into predicates."""
    out: list[ApplicabilityPredicate] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError(f"applicability predicate must be a mapping, got {type(item).__name__}")
        out.append(ApplicabilityPredicate(
            field_path=item.get("field_path") or item.get("field") or "",
            operator=PredicateOperator(item.get("operator", "equals")),
            value=item.get("value"),
        ))
    return tuple(out)
