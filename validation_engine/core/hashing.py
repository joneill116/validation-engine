"""
Stable, content-addressable hashing for audit and replay.

The same logical value must always produce the same hash, regardless of:
  - dict key insertion order
  - tuple vs list (both -> ordered sequence)
  - frozen vs mutable mapping (MappingProxyType / dict / Mapping)
  - dataclass identity (only field values matter)
  - enum identity (.value used for hashing)
  - ``Decimal`` numeric precision (exact string form preserved, no float drift)
  - ``datetime`` / ``date`` (ISO-8601 form)

Used by ``ValidationManifest`` to prove that a given payload + ruleset +
profile + contract snapshot + reference snapshots produced a particular
``ValidationResult``.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
import json
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


# Sentinel inserted into the canonical form to distinguish container kinds
# that would otherwise collide once turned into JSON. Kept short and
# unlikely to collide with payload content.
_SET_TAG = "__set__"


def canonicalize(value: Any) -> Any:
    """
    Turn ``value`` into a JSON-friendly Python structure with stable ordering.

    The output is composed only of: ``dict`` (with sorted string keys),
    ``list``, ``str``, ``int``, ``float``, ``bool``, and ``None``. All other
    inputs (dataclasses, enums, sets, frozensets, mappings, dates, decimals)
    are normalized into that vocabulary.
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        # Reject non-finite floats: they would serialize as "NaN"/"Infinity"
        # under non-strict JSON and silently break hash equality. Decimal
        # already rejects them in to_decimal(); mirror that here.
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"non-finite float cannot be hashed: {value!r}")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"non-finite Decimal cannot be hashed: {value!r}")
        # ``str(Decimal)`` preserves the exact representation including
        # trailing zeros, so 1.10 and 1.1 hash differently. That is the
        # right behaviour: they are distinct ``Decimal`` values.
        return str(value)
    if isinstance(value, _dt.datetime):
        # Normalize naive vs aware to a single ISO form.
        return value.isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, Enum):
        return canonicalize(value.value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _canonicalize_dataclass(value)
    if isinstance(value, (Mapping, MappingProxyType)):
        return _canonicalize_mapping(value)
    if isinstance(value, (set, frozenset)):
        # Tag sets so they don't collide with lists/tuples sharing the
        # same elements but different semantics.
        items = [canonicalize(v) for v in value]
        items.sort(key=_sort_key)
        return {_SET_TAG: items}
    if isinstance(value, (list, tuple)):
        return [canonicalize(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    raise TypeError(
        f"cannot canonicalize value of type {type(value).__name__}: {value!r}"
    )


def canonical_json(value: Any) -> str:
    """Return the canonical JSON encoding of ``value``."""
    return json.dumps(
        canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def stable_hash(value: Any, *, algorithm: str = "sha256") -> str:
    """Return a hex SHA-256 (by default) of the canonical form of ``value``."""
    h = hashlib.new(algorithm)
    h.update(canonical_json(value).encode("utf-8"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------

def _canonicalize_dataclass(value: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in dataclasses.fields(value):
        out[f.name] = canonicalize(getattr(value, f.name))
    return dict(sorted(out.items()))


def _canonicalize_mapping(value: Mapping[Any, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in value.items():
        if not isinstance(k, str):
            raise TypeError(
                f"mapping keys must be strings for stable hashing, got {type(k).__name__}"
            )
        out[k] = canonicalize(v)
    return dict(sorted(out.items()))


def _sort_key(value: Any) -> tuple[int, str]:
    """Stable ordering for canonicalized values inside sets."""
    # Tier by type to avoid TypeError when mixing primitives.
    tier = {bool: 0, int: 1, float: 2, str: 3}.get(type(value), 4)
    return (tier, json.dumps(value, sort_keys=True, ensure_ascii=False))
