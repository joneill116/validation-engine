"""Tests for stable canonicalization and hashing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType

import pytest

from validation_engine.core.hashing import canonical_json, canonicalize, stable_hash


class _Color(Enum):
    RED = "red"
    BLUE = "blue"


@dataclass(frozen=True)
class _Sample:
    name: str
    score: Decimal
    color: _Color
    tags: tuple[str, ...]


class TestCanonicalize:
    def test_dict_key_order_does_not_affect_output(self):
        a = {"b": 1, "a": 2}
        b = {"a": 2, "b": 1}
        assert canonical_json(a) == canonical_json(b)

    def test_mappingproxy_and_dict_match(self):
        d = {"x": 1, "y": [1, 2]}
        mp = MappingProxyType(dict(d))
        assert canonical_json(d) == canonical_json(mp)

    def test_nested_dict_key_order_normalized(self):
        a = {"outer": {"y": 1, "x": 2}}
        b = {"outer": {"x": 2, "y": 1}}
        assert stable_hash(a) == stable_hash(b)

    def test_list_order_is_significant(self):
        assert stable_hash([1, 2, 3]) != stable_hash([3, 2, 1])

    def test_set_normalized_to_sorted(self):
        # Sets serialize independent of insertion order.
        a = {1, 2, 3}
        b = {3, 1, 2}
        assert stable_hash(a) == stable_hash(b)

    def test_tuple_and_list_share_canonical_form(self):
        # Both serialize to a JSON list.
        assert canonicalize((1, 2, 3)) == canonicalize([1, 2, 3])

    def test_decimal_preserves_precision(self):
        # 1.10 and 1.1 are distinct Decimals; their hashes differ.
        assert stable_hash(Decimal("1.10")) != stable_hash(Decimal("1.1"))

    def test_decimal_does_not_drift_via_float(self):
        # Float would round 0.1 + 0.2 to 0.30000000000000004; Decimal must not.
        assert stable_hash(Decimal("0.3")) == stable_hash(Decimal("0.3"))

    def test_enum_value_preserved(self):
        assert canonicalize(_Color.RED) == "red"

    def test_dataclass_field_order_does_not_matter(self):
        a = _Sample(name="x", score=Decimal("1.0"), color=_Color.RED, tags=("a", "b"))
        b = _Sample(name="x", score=Decimal("1.0"), color=_Color.RED, tags=("a", "b"))
        assert stable_hash(a) == stable_hash(b)

    def test_datetime_iso_form(self):
        dt = datetime(2026, 1, 2, 3, 4, 5)
        assert canonicalize(dt) == "2026-01-02T03:04:05"

    def test_date_iso_form(self):
        assert canonicalize(date(2026, 1, 2)) == "2026-01-02"

    def test_non_string_keys_rejected(self):
        with pytest.raises(TypeError):
            canonicalize({1: "a"})

    def test_non_finite_decimal_rejected(self):
        with pytest.raises(ValueError):
            canonicalize(Decimal("NaN"))

    def test_non_finite_float_rejected(self):
        with pytest.raises(ValueError):
            canonicalize(float("inf"))

    def test_unsupported_type_rejected(self):
        class Custom:
            pass

        with pytest.raises(TypeError):
            canonicalize(Custom())


class TestStableHash:
    def test_changing_a_field_changes_the_hash(self):
        a = _Sample(name="x", score=Decimal("1"), color=_Color.RED, tags=())
        b = _Sample(name="y", score=Decimal("1"), color=_Color.RED, tags=())
        assert stable_hash(a) != stable_hash(b)

    def test_hash_is_hex_sha256_default(self):
        h = stable_hash({"a": 1})
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
