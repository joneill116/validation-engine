"""
Phase 4 tests:
  - RuleApplicability predicates and engine integration (NOT_APPLICABLE)
  - RuleDependency: REQUIRES_PASS / REQUIRES_RUN / SKIP_IF_FAILED
  - Compiler validates dependency graph (missing IDs, cycles)
  - rule_groups: YAML loading + group default severity/category cascade
  - ValidationProfile model
  - ValidationSummary new aggregations (by_severity / by_finding_code / etc.)
"""
from __future__ import annotations

import textwrap

import pytest

from validation_engine import (
    ApplicabilityPredicate,
    Category,
    ConfigLoader,
    DependencyMode,
    PredicateOperator,
    RuleApplicability,
    RuleDependency,
    RuleExecutionStatus,
    RulesetCompiler,
    Severity,
    SeverityGateStrategy,
    ValidationEngine,
    ValidationProfile,
    ValidationRequest,
)
from validation_engine.config.schema import RuleConfig, RulesetConfig, StrategyConfig


def _yaml_available() -> bool:
    try:
        import yaml  # noqa: F401
        return True
    except ImportError:
        return False


def _config_with_rules(*rules):
    return RulesetConfig(
        ruleset_id="rs1", ruleset_version="v1", entity_type="record",
        rules=tuple(rules),
        strategy=StrategyConfig(strategy_type="severity_gate"),
    )


def _engine_from(cfg):
    compiled = RulesetCompiler().compile(cfg)
    return ValidationEngine(rules=list(compiled.rules), strategy=compiled.strategy)


def _request(entities):
    return ValidationRequest(
        entity_type="record", ruleset_id="rs1",
        payload={"entities": entities},
    )


# ---------------------------------------------------------------------------
# RuleApplicability — predicate evaluation in isolation
# ---------------------------------------------------------------------------


class TestApplicabilityPredicates:
    def test_equals(self):
        ap = RuleApplicability(predicates=(
            ApplicabilityPredicate("instrument_type", PredicateOperator.EQUALS, "bond"),
        ))
        assert ap.evaluate({"instrument_type": "bond"}) is True
        assert ap.evaluate({"instrument_type": "equity"}) is False

    def test_in(self):
        ap = RuleApplicability(predicates=(
            ApplicabilityPredicate("side", PredicateOperator.IN, ["BUY", "SELL"]),
        ))
        assert ap.evaluate({"side": "BUY"}) is True
        assert ap.evaluate({"side": "ROLL"}) is False

    def test_in_requires_collection_value(self):
        with pytest.raises(ValueError):
            ApplicabilityPredicate("x", PredicateOperator.IN, "not_a_list")

    def test_exists_vs_is_null(self):
        ap_exists = RuleApplicability(predicates=(
            ApplicabilityPredicate("coupon_rate", PredicateOperator.EXISTS),
        ))
        ap_not_null = RuleApplicability(predicates=(
            ApplicabilityPredicate("coupon_rate", PredicateOperator.IS_NOT_NULL),
        ))
        # EXISTS only checks for the key.
        assert ap_exists.evaluate({"coupon_rate": None}) is True
        # IS_NOT_NULL rejects None.
        assert ap_not_null.evaluate({"coupon_rate": None}) is False

    def test_match_any(self):
        ap = RuleApplicability(
            predicates=(
                ApplicabilityPredicate("a", PredicateOperator.EQUALS, 1),
                ApplicabilityPredicate("b", PredicateOperator.EQUALS, 2),
            ),
            match="any",
        )
        assert ap.evaluate({"a": 1}) is True
        assert ap.evaluate({"b": 2}) is True
        assert ap.evaluate({"a": 99, "b": 99}) is False

    def test_unconditional_passes_everything(self):
        ap = RuleApplicability()
        assert ap.is_unconditional is True
        assert ap.evaluate({}) is True

    def test_heterogeneous_comparison_returns_false(self):
        # str vs int comparison would TypeError; we treat that as "predicate
        # didn't match" rather than letting it explode.
        ap = RuleApplicability(predicates=(
            ApplicabilityPredicate("amt", PredicateOperator.GREATER_THAN, 10),
        ))
        assert ap.evaluate({"amt": "abc"}) is False


# ---------------------------------------------------------------------------
# Engine: applicability gates rule execution
# ---------------------------------------------------------------------------


class TestEngineHonoursApplicability:
    def test_field_rule_skipped_when_predicate_false(self):
        cfg = _config_with_rules(RuleConfig(
            rule_id="r.required_when_bond",
            rule_type="not_null",
            field_path="coupon_rate",
            applies_when=RuleApplicability(predicates=(
                ApplicabilityPredicate(
                    "instrument_type", PredicateOperator.EQUALS, "bond",
                ),
            )),
        ))
        engine = _engine_from(cfg)
        result = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {
                "instrument_type": "equity", "coupon_rate": None,
            }},
        ]))
        rr = next(r for r in result.rule_results if r.rule_id == "r.required_when_bond")
        # Predicate did not match -> rule must NOT_APPLICABLE, not failed.
        assert rr.status is RuleExecutionStatus.NOT_APPLICABLE
        assert result.summary.not_applicable_count == 1

    def test_field_rule_runs_when_predicate_true(self):
        cfg = _config_with_rules(RuleConfig(
            rule_id="r.required_when_bond",
            rule_type="not_null",
            field_path="coupon_rate",
            applies_when=RuleApplicability(predicates=(
                ApplicabilityPredicate(
                    "instrument_type", PredicateOperator.EQUALS, "bond",
                ),
            )),
        ))
        engine = _engine_from(cfg)
        result = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {
                "instrument_type": "bond", "coupon_rate": None,
            }},
        ]))
        rr = next(r for r in result.rule_results if r.rule_id == "r.required_when_bond")
        # Predicate matched -> rule ran, found a null value -> failed.
        assert rr.status is RuleExecutionStatus.FAILED


# ---------------------------------------------------------------------------
# Dependency graph validation
# ---------------------------------------------------------------------------


class TestDependencyGraphValidation:
    def test_missing_dependency_rejected(self):
        cfg = _config_with_rules(RuleConfig(
            rule_id="r.b", rule_type="required", field_path="x",
            depends_on=(RuleDependency(rule_id="r.does_not_exist"),),
        ))
        with pytest.raises(ValueError, match="depends on unknown rule"):
            RulesetCompiler().compile(cfg)

    def test_cycle_rejected(self):
        cfg = _config_with_rules(
            RuleConfig(
                rule_id="r.a", rule_type="required", field_path="x",
                depends_on=(RuleDependency(rule_id="r.b"),),
            ),
            RuleConfig(
                rule_id="r.b", rule_type="required", field_path="y",
                depends_on=(RuleDependency(rule_id="r.a"),),
            ),
        )
        with pytest.raises(ValueError, match="cycle"):
            RulesetCompiler().compile(cfg)


# ---------------------------------------------------------------------------
# Engine: dependency-aware sequencing
# ---------------------------------------------------------------------------


class TestRuleDependencyExecution:
    def test_dependent_skipped_when_prereq_failed(self):
        cfg = _config_with_rules(
            # Prereq fails (field is missing)
            RuleConfig(
                rule_id="r.prereq", rule_type="required", field_path="needed",
            ),
            # Dependent requires prereq to PASS — must be skipped.
            RuleConfig(
                rule_id="r.dependent", rule_type="not_null", field_path="other",
                depends_on=(RuleDependency(rule_id="r.prereq", mode=DependencyMode.REQUIRES_PASS),),
            ),
        )
        engine = _engine_from(cfg)
        result = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {"other": "value"}},
        ]))
        prereq = next(r for r in result.rule_results if r.rule_id == "r.prereq")
        dep = next(r for r in result.rule_results if r.rule_id == "r.dependent")
        assert prereq.status is RuleExecutionStatus.FAILED
        assert dep.status is RuleExecutionStatus.SKIPPED
        assert dep.skip_reason and dep.skip_reason.startswith("dependency_failed")

    def test_dependent_runs_when_prereq_passed(self):
        cfg = _config_with_rules(
            RuleConfig(
                rule_id="r.prereq", rule_type="required", field_path="needed",
            ),
            RuleConfig(
                rule_id="r.dependent", rule_type="not_null", field_path="other",
                depends_on=(RuleDependency(rule_id="r.prereq"),),
            ),
        )
        engine = _engine_from(cfg)
        result = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {
                "needed": "x", "other": "value",
            }},
        ]))
        dep = next(r for r in result.rule_results if r.rule_id == "r.dependent")
        assert dep.status is RuleExecutionStatus.PASSED


# ---------------------------------------------------------------------------
# rule_groups loading
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _yaml_available(), reason="PyYAML not installed")
class TestRuleGroupsYAML:
    def test_group_defaults_cascade(self):
        yaml_text = textwrap.dedent("""
            ruleset_id: rs1
            ruleset_version: v1
            entity_type: record
            rule_groups:
              - group_id: structural
                default_severity: blocking
                default_category: structural
                rules:
                  - rule_id: r.acct.required
                    rule_type: required
                    field_path: account_id
        """)
        cfg = ConfigLoader().loads(yaml_text, fmt="yaml")
        # The group rule was flattened into ruleset.rules with the group_id stamped.
        flat = next(r for r in cfg.rules if r.rule_id == "r.acct.required")
        assert flat.group_id == "structural"
        assert flat.severity is Severity.BLOCKING
        assert flat.category is Category.STRUCTURAL

    def test_disabled_group_disables_member_rules(self):
        yaml_text = textwrap.dedent("""
            ruleset_id: rs1
            ruleset_version: v1
            entity_type: record
            rule_groups:
              - group_id: structural
                enabled: false
                rules:
                  - rule_id: r.acct.required
                    rule_type: required
                    field_path: account_id
        """)
        cfg = ConfigLoader().loads(yaml_text, fmt="yaml")
        flat = next(r for r in cfg.rules if r.rule_id == "r.acct.required")
        assert flat.enabled is False
        # Compiling should silently drop the disabled rule.
        compiled = RulesetCompiler().compile(cfg)
        assert all(r.rule_id != "r.acct.required" for r in compiled.rules)


# ---------------------------------------------------------------------------
# ValidationProfile
# ---------------------------------------------------------------------------


class TestValidationProfile:
    def test_minimal(self):
        p = ValidationProfile(profile_id="p1", profile_version="v1")
        assert p.profile_id == "p1"
        assert p.default_severity is Severity.BLOCKING
        assert p.default_category is Category.BUSINESS_RULE

    def test_required_fields(self):
        with pytest.raises(ValueError):
            ValidationProfile(profile_id="", profile_version="v1")
        with pytest.raises(ValueError):
            ValidationProfile(profile_id="p", profile_version="")

    def test_string_severity_coerced(self):
        # The YAML loader will hand us strings for severity/category.
        p = ValidationProfile(
            profile_id="p", profile_version="v1",
            default_severity="warning",
            default_category="completeness",
        )
        assert p.default_severity is Severity.WARNING
        assert p.default_category is Category.COMPLETENESS


# ---------------------------------------------------------------------------
# ValidationSummary new aggregations
# ---------------------------------------------------------------------------


class TestSummaryAggregations:
    def test_by_finding_code_and_field_path(self):
        cfg = _config_with_rules(
            RuleConfig(
                rule_id="r.acct", rule_type="required", field_path="account_id",
            ),
            RuleConfig(
                rule_id="r.amt", rule_type="not_null", field_path="amount",
            ),
        )
        engine = _engine_from(cfg)
        # Both rules will fail on this entity.
        result = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {"amount": None}},
        ]))
        s = result.summary
        # account_id failed via REQUIRED_FIELD_MISSING; amount via the
        # not_null finding code (also REQUIRED_FIELD_MISSING by default).
        assert s.by_finding_code["REQUIRED_FIELD_MISSING"] == 2
        # field_path aggregation — both fields appear.
        assert s.by_field_path.get("account_id") == 1
        assert s.by_field_path.get("amount") == 1
        # rule_id aggregation
        assert s.by_rule_id["r.acct"] == 1
        assert s.by_rule_id["r.amt"] == 1
        # severity aggregation (both BLOCKING)
        assert s.by_severity["blocking"] == 2

    def test_by_rule_group_when_group_set(self):
        # Rule attached to a group → group_id propagates to RuleResult,
        # which lets the summary roll up by group.
        cfg = _config_with_rules(RuleConfig(
            rule_id="r.acct", rule_type="required", field_path="account_id",
            group_id="structural",
        ))
        engine = _engine_from(cfg)
        result = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {}},
        ]))
        assert result.summary.by_rule_group.get("structural") == 1
