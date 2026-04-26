"""Tests for standard configurable rule types."""
import pytest

from validation_engine import (
    EvaluationContext,
    RuleFactory,
    ValidationRequest,
)
from validation_engine.config.schema import RuleConfig


def _ctx(entity_type="record", reference_data=None):
    req = ValidationRequest(
        entity_type=entity_type, ruleset_id="rs1",
        payload={"entities": []},
    )
    return EvaluationContext(
        request=req,
        ruleset_id="rs1", ruleset_version="v1",
        reference_data=reference_data or {},
    )


def _build(rule_type, rule_id="r", **kw):
    factory = RuleFactory()
    cfg = RuleConfig(rule_id=rule_id, rule_type=rule_type, **kw)
    return factory.build(cfg)


# ─── required ────────────────────────────────────────────────────────────────


class TestRequired:
    def test_passes_when_present(self):
        rule = _build("required", field_path="acct")
        finding = rule.evaluate({"fields": {"acct": "A1"}}, _ctx())
        assert finding.passed is True

    def test_fails_when_missing(self):
        rule = _build("required", field_path="acct")
        finding = rule.evaluate({"fields": {}}, _ctx())
        assert finding.passed is False
        assert finding.field_path == "acct"

    def test_requires_field_path(self):
        with pytest.raises(ValueError):
            _build("required")  # no field_path -> error


# ─── not_null ────────────────────────────────────────────────────────────────


class TestNotNull:
    def test_passes_with_value(self):
        rule = _build("not_null", field_path="acct")
        finding = rule.evaluate("A1", _ctx())
        assert finding.passed is True

    def test_fails_on_none(self):
        rule = _build("not_null", field_path="acct")
        assert rule.evaluate(None, _ctx()).passed is False

    def test_fails_on_empty_string(self):
        rule = _build("not_null", field_path="acct")
        assert rule.evaluate("   ", _ctx()).passed is False

    def test_allow_empty(self):
        rule = _build("not_null", field_path="acct", params={"allow_empty": True})
        assert rule.evaluate("", _ctx()).passed is True


# ─── enum ────────────────────────────────────────────────────────────────────


class TestEnum:
    def test_membership(self):
        rule = _build("enum", field_path="side", params={"values": ["A", "B"]})
        assert rule.evaluate("A", _ctx()).passed is True
        assert rule.evaluate("Z", _ctx()).passed is False

    def test_case_insensitive(self):
        rule = _build("enum", field_path="side", params={"values": ["A"], "case_sensitive": False})
        assert rule.evaluate("a", _ctx()).passed is True


# ─── range ───────────────────────────────────────────────────────────────────


class TestRange:
    def test_inclusive_bounds(self):
        rule = _build("range", field_path="amt", params={"min": 0, "max": 100})
        assert rule.evaluate(0, _ctx()).passed is True
        assert rule.evaluate(100, _ctx()).passed is True
        assert rule.evaluate(101, _ctx()).passed is False

    def test_exclusive_bounds(self):
        rule = _build(
            "range", field_path="amt",
            params={"min": 0, "max": 100, "inclusive_min": False, "inclusive_max": False},
        )
        assert rule.evaluate(0, _ctx()).passed is False
        assert rule.evaluate(50, _ctx()).passed is True

    def test_non_numeric(self):
        rule = _build("range", field_path="amt", params={"min": 0, "max": 100})
        assert rule.evaluate("abc", _ctx()).passed is False


# ─── regex ───────────────────────────────────────────────────────────────────


class TestRegex:
    def test_iso4217(self):
        rule = _build("regex", field_path="ccy", params={"pattern": "^[A-Z]{3}$"})
        assert rule.evaluate("USD", _ctx()).passed is True
        assert rule.evaluate("usd", _ctx()).passed is False

    def test_non_string(self):
        rule = _build("regex", field_path="ccy", params={"pattern": "^[A-Z]{3}$"})
        assert rule.evaluate(123, _ctx()).passed is False


# ─── comparison ──────────────────────────────────────────────────────────────


class TestComparison:
    def test_gte(self):
        rule = _build("comparison", params={"left": "field_a", "right": "field_b", "operator": "gte"})
        entity = {"fields": {"field_b": "2026-04-01", "field_a": "2026-04-03"}}
        assert rule.evaluate(entity, _ctx()).passed is True

    def test_lt_failure(self):
        rule = _build("comparison", params={"left": "a", "right": "b", "operator": "lt"})
        entity = {"fields": {"a": 5, "b": 5}}
        assert rule.evaluate(entity, _ctx()).passed is False

    def test_unknown_operator(self):
        with pytest.raises(ValueError):
            _build("comparison", params={"left": "a", "right": "b", "operator": "xx"})


# ─── date_between ────────────────────────────────────────────────────────────


class TestDateBetween:
    def test_in_window(self):
        rule = _build(
            "date_between", field_path="d",
            params={"window_ref": "win"},
        )
        ctx = _ctx(reference_data={"win": {"start": "2026-01-01", "end": "2026-12-31"}})
        assert rule.evaluate("2026-06-15", ctx).passed is True
        assert rule.evaluate("2025-12-31", ctx).passed is False


# ─── unique ──────────────────────────────────────────────────────────────────


class TestUnique:
    def test_no_duplicates(self):
        rule = _build("unique", params={"field": "txn_id"})
        entities = [
            {"fields": {"txn_id": "a"}},
            {"fields": {"txn_id": "b"}},
        ]
        findings = list(rule.evaluate(entities, _ctx()))
        assert all(f.passed for f in findings)

    def test_with_duplicates(self):
        rule = _build("unique", params={"field": "txn_id"})
        entities = [
            {"fields": {"txn_id": "a"}, "entity_ref": {"id": "1"}},
            {"fields": {"txn_id": "a"}, "entity_ref": {"id": "2"}},
        ]
        findings = list(rule.evaluate(entities, _ctx()))
        assert any(not f.passed for f in findings)


# ─── conditional_required ────────────────────────────────────────────────────


class TestConditionalRequired:
    def test_required_when_condition_matches(self):
        rule = _build(
            "conditional_required",
            params={"when_field": "trigger", "when_in": ["A"], "require": "dependent"},
        )
        entity = {"fields": {"trigger": "A"}}
        assert rule.evaluate(entity, _ctx()).passed is False

    def test_skipped_when_condition_does_not_match(self):
        rule = _build(
            "conditional_required",
            params={"when_field": "trigger", "when_in": ["A"], "require": "dependent"},
        )
        entity = {"fields": {"trigger": "OTHER"}}
        assert rule.evaluate(entity, _ctx()).passed is True

    def test_required_when_present(self):
        rule = _build(
            "conditional_required",
            params={"when_field": "trigger", "when_in": ["A"], "require": "dependent"},
        )
        entity = {"fields": {"trigger": "A", "dependent": "X"}}
        assert rule.evaluate(entity, _ctx()).passed is True


# ─── sum_equals ──────────────────────────────────────────────────────────────


class TestSumEquals:
    def test_matches_constant(self):
        rule = _build(
            "sum_equals",
            params={"amount_field": "amt", "expected_value": "100"},
        )
        entities = [
            {"fields": {"amt": 60}},
            {"fields": {"amt": 40}},
        ]
        findings = list(rule.evaluate(entities, _ctx()))
        assert findings[0].passed is True

    def test_within_tolerance(self):
        rule = _build(
            "sum_equals",
            params={"amount_field": "amt", "expected_value": "100", "tolerance": "0.05"},
        )
        entities = [{"fields": {"amt": 100.04}}]
        findings = list(rule.evaluate(entities, _ctx()))
        assert findings[0].passed is True

    def test_does_not_match(self):
        rule = _build(
            "sum_equals",
            params={"amount_field": "amt", "expected_value": "100"},
        )
        entities = [{"fields": {"amt": 50}}]
        findings = list(rule.evaluate(entities, _ctx()))
        assert findings[0].passed is False

    def test_non_numeric_surfaces_finding(self):
        rule = _build(
            "sum_equals",
            params={"amount_field": "amt", "expected_value": "100"},
        )
        entities = [
            {"fields": {"amt": "oops"}, "entity_ref": {"id": "1"}},
            {"fields": {"amt": 100}},
        ]
        findings = list(rule.evaluate(entities, _ctx()))
        assert any(
            not f.passed and "Non-numeric" in f.message for f in findings
        ), [f.message for f in findings]

    def test_nan_surfaces_finding(self):
        # NaN would poison sums and break tolerance comparisons; must be rejected.
        rule = _build(
            "sum_equals",
            params={"amount_field": "amt", "expected_value": "100"},
        )
        entities = [
            {"fields": {"amt": "NaN"}, "entity_ref": {"id": "1"}},
            {"fields": {"amt": 100}},
        ]
        findings = list(rule.evaluate(entities, _ctx()))
        assert any(
            not f.passed and "non-finite" in f.message.lower() for f in findings
        ), [f.message for f in findings]
