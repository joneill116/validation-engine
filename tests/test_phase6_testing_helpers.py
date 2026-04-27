"""
Phase 6 tests for the testing helpers (builders, assertions, golden) plus
end-to-end golden snapshots for representative scenarios.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from validation_engine import (
    Category,
    RuleConfig,
    RuleExecutionStatus,
    RulesetCompiler,
    RulesetConfig,
    Severity,
    SeverityGateStrategy,
    StrategyConfig,
    ValidationEngine,
    ValidationRequest,
    finding_codes,
)
from validation_engine.testing import (
    assert_failed,
    assert_has_finding,
    assert_matches_golden,
    assert_passed,
    assert_rule_status,
    entity_builder,
    finding_builder,
    request_builder,
    ruleset_builder,
)


GOLDEN_DIR = Path(__file__).parent / "golden"


# ─── builders ──────────────────────────────────────────────────────────────


class TestBuilders:
    def test_entity_builder_normalizes_id(self):
        e = entity_builder(entity_id="e1", fields={"x": 1})
        assert e["entity_ref"]["id"] == "e1"
        assert e["fields"]["x"] == 1

    def test_request_builder(self):
        req = request_builder(entities=[entity_builder(entity_id="e1", fields={"x": 1})])
        assert req.entity_type == "record"
        assert len(req.payload["entities"]) == 1

    def test_ruleset_builder(self):
        rs = ruleset_builder(rules=[
            RuleConfig(rule_id="r.a", rule_type="required", field_path="x"),
        ])
        assert rs.ruleset_id == "rs1"
        assert len(rs.rules) == 1

    def test_finding_builder_default_failed(self):
        f = finding_builder()
        assert f.passed is False
        assert f.severity is Severity.BLOCKING


# ─── assertions ─────────────────────────────────────────────────────────────


def _engine_from_cfg(cfg):
    compiled = RulesetCompiler().compile(cfg)
    return ValidationEngine(rules=list(compiled.rules), strategy=compiled.strategy)


class TestAssertions:
    def test_assert_passed_on_clean_run(self):
        cfg = ruleset_builder(rules=[
            RuleConfig(rule_id="r.a", rule_type="required", field_path="x"),
        ])
        engine = _engine_from_cfg(cfg)
        result = engine.validate(request_builder(entities=[
            entity_builder(entity_id="1", fields={"x": "v"}),
        ]))
        assert_passed(result)

    def test_assert_failed_when_blocking_finding(self):
        cfg = ruleset_builder(rules=[
            RuleConfig(rule_id="r.a", rule_type="required", field_path="x"),
        ])
        engine = _engine_from_cfg(cfg)
        result = engine.validate(request_builder(entities=[
            entity_builder(entity_id="1", fields={}),
        ]))
        assert_failed(result)

    def test_assert_passed_raises_on_failed_run(self):
        cfg = ruleset_builder(rules=[
            RuleConfig(rule_id="r.a", rule_type="required", field_path="x"),
        ])
        engine = _engine_from_cfg(cfg)
        result = engine.validate(request_builder(entities=[
            entity_builder(entity_id="1", fields={}),
        ]))
        with pytest.raises(AssertionError):
            assert_passed(result)

    def test_assert_has_finding_by_code(self):
        cfg = ruleset_builder(rules=[
            RuleConfig(rule_id="r.a", rule_type="required", field_path="x"),
        ])
        engine = _engine_from_cfg(cfg)
        result = engine.validate(request_builder(entities=[
            entity_builder(entity_id="1", fields={}),
        ]))
        assert_has_finding(result, code=finding_codes.REQUIRED_FIELD_MISSING)

    def test_assert_has_finding_misses_helpful_error(self):
        cfg = ruleset_builder(rules=[
            RuleConfig(rule_id="r.a", rule_type="required", field_path="x"),
        ])
        engine = _engine_from_cfg(cfg)
        result = engine.validate(request_builder(entities=[
            entity_builder(entity_id="1", fields={}),
        ]))
        with pytest.raises(AssertionError, match="no failed finding matched"):
            assert_has_finding(result, code="NEVER_RAISED")

    def test_assert_rule_status(self):
        cfg = ruleset_builder(rules=[
            RuleConfig(rule_id="r.a", rule_type="required", field_path="x"),
        ])
        engine = _engine_from_cfg(cfg)
        result = engine.validate(request_builder(entities=[
            entity_builder(entity_id="1", fields={"x": "v"}),
        ]))
        assert_rule_status(result, "r.a", RuleExecutionStatus.PASSED)


# ─── golden snapshots ──────────────────────────────────────────────────────


class TestGolden:
    def test_simple_clean_run_round_trips_to_golden(self, tmp_path):
        """First run writes the snapshot; subsequent runs match it."""
        cfg = ruleset_builder(rules=[
            RuleConfig(rule_id="r.required", rule_type="required", field_path="acct"),
            RuleConfig(
                rule_id="r.enum", rule_type="enum",
                field_path="status",
                params={"values": ["A", "B"]},
            ),
        ])
        engine = _engine_from_cfg(cfg)
        result = engine.validate(request_builder(entities=[
            entity_builder(entity_id="1", fields={"acct": "A1", "status": "A"}),
            entity_builder(entity_id="2", fields={"acct": "A2", "status": "B"}),
        ]))

        golden_path = tmp_path / "clean.json"
        # First call: writes the snapshot AND fails (so the author reviews).
        with pytest.raises(AssertionError, match="initial snapshot"):
            assert_matches_golden(result, golden_path)
        # Second call against the same snapshot now passes.
        assert_matches_golden(result, golden_path)

    def test_failure_run_with_blocking_finding(self, tmp_path):
        cfg = ruleset_builder(rules=[
            RuleConfig(rule_id="r.required", rule_type="required", field_path="acct"),
        ])
        engine = _engine_from_cfg(cfg)
        result = engine.validate(request_builder(entities=[
            entity_builder(entity_id="1", fields={}),
        ]))
        golden_path = tmp_path / "failure.json"
        # Bootstrap.
        with pytest.raises(AssertionError, match="initial snapshot"):
            assert_matches_golden(result, golden_path)
        # Re-running the same logic produces the same logical snapshot.
        result2 = engine.validate(request_builder(entities=[
            entity_builder(entity_id="1", fields={}),
        ]))
        assert_matches_golden(result2, golden_path)
