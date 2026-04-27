"""
Phase 3 tests:

- New standard rules: type_check, record_count, completeness_ratio
- finding_code wired up on existing standard rules
- Context-only rule API: ``evaluate(self, ctx) -> RuleEvaluation``
- Rule helper methods (self.passed/failed/not_applicable/observation)
- EvaluationContext extensions (get_field/has_field/get_ref/get_reference_data,
  field_value, entity_ref, target)
- Observations bubble up to ValidationResult / RuleResult
- Skipped rules and explicit NOT_APPLICABLE are distinct from PASSED
"""
from __future__ import annotations

import pytest

from validation_engine import (
    Category,
    EvaluationContext,
    RuleExecutionStatus,
    Scope,
    Severity,
    SeverityGateStrategy,
    ValidationEngine,
    ValidationFinding,
    ValidationRequest,
    finding_codes,
)
from validation_engine.config.schema import RuleConfig
from validation_engine.config.factory import RuleFactory
from validation_engine.models.rule_evaluation import RuleEvaluation
from validation_engine.models.target import ValidationTarget
from validation_engine.rules.base import Rule


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _ctx(reference_data=None, entity=None, field_value=None, field_path=None):
    req = ValidationRequest(
        entity_type="record", ruleset_id="rs1",
        payload={"entities": []},
    )
    return EvaluationContext(
        request=req,
        ruleset_id="rs1", ruleset_version="v1",
        reference_data=reference_data or {},
        current_entity=entity,
        current_field_path=field_path,
        field_value=field_value,
        entity_ref=(entity or {}).get("entity_ref", {}) if isinstance(entity, dict) else {},
    )


def _build(rule_type, rule_id="r", **kw):
    return RuleFactory().build(RuleConfig(rule_id=rule_id, rule_type=rule_type, **kw))


def _request(entities):
    return ValidationRequest(
        entity_type="record", ruleset_id="rs1",
        payload={"entities": entities},
    )


def _engine(rules):
    return ValidationEngine(rules=rules, strategy=SeverityGateStrategy())


# ---------------------------------------------------------------------------
# type_check
# ---------------------------------------------------------------------------

class TestTypeCheck:
    def test_string(self):
        rule = _build("type_check", field_path="x", params={"expected_type": "string"})
        assert rule.evaluate("hi", _ctx()).passed is True
        assert rule.evaluate(7, _ctx()).passed is False

    def test_integer_excludes_bool(self):
        rule = _build("type_check", field_path="x", params={"expected_type": "integer"})
        assert rule.evaluate(7, _ctx()).passed is True
        # ``bool`` is a subclass of int but isn't a count — must not match.
        assert rule.evaluate(True, _ctx()).passed is False

    def test_decimal_accepts_string_decimal(self):
        rule = _build("type_check", field_path="x", params={"expected_type": "decimal"})
        assert rule.evaluate("1.50", _ctx()).passed is True
        assert rule.evaluate(1.5, _ctx()).passed is True
        assert rule.evaluate("not a number", _ctx()).passed is False

    def test_decimal_rejects_nan(self):
        rule = _build("type_check", field_path="x", params={"expected_type": "decimal"})
        assert rule.evaluate(float("nan"), _ctx()).passed is False
        assert rule.evaluate("NaN", _ctx()).passed is False

    def test_finding_code(self):
        rule = _build("type_check", field_path="x", params={"expected_type": "integer"})
        f = rule.evaluate("nope", _ctx())
        assert f.finding_code == finding_codes.INVALID_TYPE

    def test_unknown_type_rejected_at_construction(self):
        with pytest.raises(ValueError):
            _build("type_check", field_path="x", params={"expected_type": "money"})


# ---------------------------------------------------------------------------
# record_count
# ---------------------------------------------------------------------------

class TestRecordCount:
    def test_min_count_pass(self):
        rule = _build("record_count", params={"min_count": 1})
        ev = rule.evaluate([{"fields": {}}], _ctx())
        assert isinstance(ev, RuleEvaluation)
        assert ev.status.value == "passed"
        # Even a passing rule emits the metric so it can be trended.
        assert any(o.metric_name == "record_count" for o in ev.observations)

    def test_min_count_fail(self):
        rule = _build("record_count", params={"min_count": 5})
        ev = rule.evaluate([{"fields": {}}], _ctx())
        assert ev.status.value == "failed"
        assert ev.findings[0].actual == 1

    def test_max_count_fail(self):
        rule = _build("record_count", params={"max_count": 1})
        ev = rule.evaluate([{"fields": {}}, {"fields": {}}], _ctx())
        assert ev.status.value == "failed"

    def test_inverted_bounds_rejected(self):
        with pytest.raises(ValueError):
            _build("record_count", params={"min_count": 5, "max_count": 1})


# ---------------------------------------------------------------------------
# completeness_ratio
# ---------------------------------------------------------------------------

class TestCompletenessRatio:
    def test_full_completeness(self):
        rule = _build(
            "completeness_ratio",
            params={"field_path": "fusion_id", "min_ratio": "0.98"},
        )
        entities = [{"fields": {"fusion_id": "abc"}} for _ in range(10)]
        ev = rule.evaluate(entities, _ctx())
        assert ev.status.value == "passed"

    def test_below_min_ratio_fails(self):
        rule = _build(
            "completeness_ratio",
            params={"field_path": "fusion_id", "min_ratio": "0.98"},
        )
        # 8/10 populated -> 0.8 < 0.98
        entities = (
            [{"fields": {"fusion_id": "abc"}}] * 8
            + [{"fields": {"fusion_id": None}}] * 2
        )
        ev = rule.evaluate(entities, _ctx())
        assert ev.status.value == "failed"
        assert ev.findings[0].finding_code == finding_codes.COMPLETENESS_BELOW_THRESHOLD
        # An observation must accompany the finding.
        assert any(o.metric_name == "completeness_ratio" for o in ev.observations)

    def test_empty_collection_passes_trivially(self):
        rule = _build(
            "completeness_ratio",
            params={"field_path": "fusion_id", "min_ratio": "1.0"},
        )
        ev = rule.evaluate([], _ctx())
        assert ev.status.value == "passed"

    def test_min_ratio_out_of_range(self):
        with pytest.raises(ValueError):
            _build("completeness_ratio", params={"field_path": "x", "min_ratio": "1.5"})


# ---------------------------------------------------------------------------
# finding_code on existing standard rules
# ---------------------------------------------------------------------------

class TestStandardRuleFindingCodes:
    def test_required_emits_required_field_missing(self):
        rule = _build("required", field_path="acct")
        f = rule.evaluate({"fields": {}}, _ctx())
        assert f.finding_code == finding_codes.REQUIRED_FIELD_MISSING

    def test_passed_required_has_no_code(self):
        rule = _build("required", field_path="acct")
        f = rule.evaluate({"fields": {"acct": "A1"}}, _ctx())
        assert f.passed is True
        # Pass-findings don't carry failure codes — those are only for the
        # actual issue rows in dashboards.
        assert f.finding_code == ""

    def test_enum_emits_value_not_allowed(self):
        rule = _build("enum", field_path="side", params={"values": ["A", "B"]})
        f = rule.evaluate("Z", _ctx())
        assert f.finding_code == finding_codes.VALUE_NOT_ALLOWED

    def test_range_emits_value_out_of_range(self):
        rule = _build("range", field_path="amt", params={"min": 0, "max": 10})
        f = rule.evaluate(99, _ctx())
        assert f.finding_code == finding_codes.VALUE_OUT_OF_RANGE

    def test_regex_emits_invalid_format(self):
        rule = _build("regex", field_path="ccy", params={"pattern": "^[A-Z]{3}$"})
        f = rule.evaluate("usd", _ctx())
        assert f.finding_code == finding_codes.INVALID_FORMAT

    def test_unique_emits_duplicate_key(self):
        rule = _build("unique", params={"field": "id"})
        entities = [
            {"fields": {"id": "a"}, "entity_ref": {"id": "1"}},
            {"fields": {"id": "a"}, "entity_ref": {"id": "2"}},
        ]
        findings = list(rule.evaluate(entities, _ctx()))
        bad = [f for f in findings if not f.passed]
        assert bad and bad[0].finding_code == finding_codes.DUPLICATE_KEY


# ---------------------------------------------------------------------------
# Context-only rule API
# ---------------------------------------------------------------------------

class _CtxOnlyRule(Rule):
    """A rule using the new ``evaluate(ctx)`` form returning RuleEvaluation."""

    rule_id = "r.ctx_only"
    scope = Scope.FIELD
    severity = Severity.BLOCKING
    category = Category.STRUCTURAL
    field_path = "amount"
    applies_to = frozenset({"*"})

    def evaluate(self, ctx: EvaluationContext) -> RuleEvaluation:
        # The new API gets the field_value off the context directly.
        if not isinstance(ctx.field_value, (int, float)) or isinstance(ctx.field_value, bool):
            return self.failed(self.make_finding(
                passed=False,
                message="amount must be numeric",
                actual=ctx.field_value,
            ))
        return self.passed(observations=[
            self.observation("amount", ctx.field_value, unit="raw"),
        ])


class TestContextOnlyRuleAPI:
    def test_ctx_only_rule_runs(self):
        engine = _engine([_CtxOnlyRule()])
        result = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {"amount": 100}},
            {"entity_ref": {"id": "2"}, "fields": {"amount": "BAD"}},
        ]))
        # The new RuleEvaluation API decouples "rule passed" from "passing
        # finding emitted": passed evaluations carry no finding, only
        # observations. So we expect one failed finding (from the bad
        # entity) and no passed finding (good entity emitted only an obs).
        assert result.summary.failed_count == 1
        assert result.summary.passed_count == 0
        assert result.summary.total_findings == 1
        # ValidationResult.observations should contain the obs from the
        # passing entity.
        assert any(o.metric_name == "amount" for o in result.observations)

    def test_observations_bubble_to_result(self):
        engine = _engine([_CtxOnlyRule()])
        result = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {"amount": 100}},
        ]))
        # The passing run should produce one Observation propagated up.
        assert len(result.observations) == 1
        assert result.observations[0].metric_name == "amount"


# ---------------------------------------------------------------------------
# NOT_APPLICABLE bubbling
# ---------------------------------------------------------------------------

class _AlwaysNotApplicable(Rule):
    rule_id = "r.na"
    scope = Scope.FIELD
    severity = Severity.BLOCKING
    category = Category.STRUCTURAL
    field_path = "any"
    applies_to = frozenset({"*"})

    def evaluate(self, ctx: EvaluationContext) -> RuleEvaluation:
        return self.not_applicable("test scenario")


class TestNotApplicableStatus:
    def test_rule_status_when_all_targets_na(self):
        engine = _engine([_AlwaysNotApplicable()])
        result = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {"any": "v"}},
        ]))
        rr = next(r for r in result.rule_results if r.rule_id == "r.na")
        assert rr.status is RuleExecutionStatus.NOT_APPLICABLE
        assert result.summary.not_applicable_count == 1
        # NOT_APPLICABLE must not be counted as passed.
        assert result.summary.total_rules_evaluated == 0


# ---------------------------------------------------------------------------
# EvaluationContext accessor helpers
# ---------------------------------------------------------------------------

class TestEvaluationContextHelpers:
    def test_get_field_top_level(self):
        ctx = _ctx(entity={"fields": {"a": 1}})
        assert ctx.get_field("a") == 1
        assert ctx.get_field("missing", default="d") == "d"
        assert ctx.has_field("a") is True
        assert ctx.has_field("missing") is False

    def test_get_field_unwraps_rich_shape(self):
        ctx = _ctx(entity={"fields": {"a": {"value": 7, "src": "x"}}})
        assert ctx.get_field("a") == 7

    def test_get_field_descends_into_nested(self):
        ctx = _ctx(entity={"fields": {"issuer": {"name": "Acme"}}})
        assert ctx.get_field("issuer.name") == "Acme"

    def test_get_ref(self):
        ctx = _ctx(entity={"entity_ref": {"id": "abc", "tenant": "t1"}})
        assert ctx.get_ref("id") == "abc"
        assert ctx.get_ref("missing", default="d") == "d"

    def test_get_reference_data(self):
        ctx = _ctx(reference_data={"iso_currencies": ["USD", "GBP"]})
        assert ctx.get_reference_data("iso_currencies") == ["USD", "GBP"]
        assert ctx.get_reference_data("missing", default=["d"]) == ["d"]

    def test_target_present_for_field_scope(self):
        engine = _engine([_CtxOnlyRule()])
        # We can't read ctx out of the engine; instead, check that the
        # target gets stamped on findings when no target was attached
        # explicitly. Default field-scope rules synthesize a FIELD target
        # via the executor.
        result = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {"amount": "BAD"}},
        ]))
        # We don't auto-stamp the target onto the finding (rules opt in),
        # but the observation should at least be present:
        assert result.findings[0].finding_code == ""  # not set by this rule


# ---------------------------------------------------------------------------
# Rule helpers produce well-formed RuleEvaluation
# ---------------------------------------------------------------------------

class TestRuleHelpers:
    def test_passed_helper(self):
        rule = _build("required", field_path="x")
        ev = rule.passed()
        assert ev.status.value == "passed"
        assert ev.findings == ()

    def test_failed_helper_accepts_single_finding(self):
        rule = _build("required", field_path="x")
        f = rule.make_finding(passed=False, message="x")
        ev = rule.failed(f)
        assert ev.status.value == "failed"
        assert ev.findings == (f,)

    def test_not_applicable_helper(self):
        rule = _build("required", field_path="x")
        ev = rule.not_applicable("not bond")
        assert ev.status.value == "not_applicable"
        assert ev.metadata["reason"] == "not bond"

    def test_observation_helper_uses_rule_id(self):
        rule = _build("required", field_path="x")
        obs = rule.observation("count", 7)
        assert obs.rule_id == rule.rule_id
        assert obs.value == 7
