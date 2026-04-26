"""Tests for ValidationResult shape and engine semantics."""
import pytest

from validation_engine import (
    Category,
    DecisionAction,
    EvaluationContext,
    RuleExecutionStatus,
    Scope,
    Severity,
    SeverityGateStrategy,
    ValidationEngine,
    ValidationError,
    ValidationFinding,
    ValidationRequest,
    ValidationStatus,
    ValidationSummary,
    Rule,
)
from validation_engine.testing import entity_rule, field_rule


def _payload():
    return {"entities": [
        {"entity_ref": {"id": "e1"}, "fields": {"x": 1}},
        {"entity_ref": {"id": "e2"}, "fields": {"x": 2}},
    ]}


class _ExplodingRule(Rule):
    rule_id = "r.boom"
    rule_version = "1.0"
    scope = Scope.ENTITY
    severity = Severity.BLOCKING
    category = Category.STRUCTURAL
    field_path = "*"
    applies_to = frozenset({"*"})

    def evaluate(self, target, ctx: EvaluationContext) -> ValidationFinding:
        raise RuntimeError("kaboom")


def _engine(rules):
    return ValidationEngine(rules=rules, strategy=SeverityGateStrategy())


def _request(entity_type="record"):
    return ValidationRequest(
        entity_type=entity_type, ruleset_id="rs1", payload=_payload(),
    )


class TestResultShape:
    def test_contains_decision_summary_findings_rule_results(self):
        result = _engine([field_rule(passes=True)]).validate(_request())
        assert result.decision is not None
        assert isinstance(result.summary, ValidationSummary)
        assert isinstance(result.findings, tuple)
        assert isinstance(result.rule_results, tuple)

    def test_status_passed_when_no_failures(self):
        result = _engine([field_rule(passes=True)]).validate(_request())
        assert result.status is ValidationStatus.PASSED
        assert result.decision.action is DecisionAction.PUBLISH
        assert result.decision.publish_allowed is True

    def test_status_passed_with_warnings(self):
        result = _engine([
            field_rule(passes=False, severity=Severity.WARNING, message="warn")
        ]).validate(_request())
        assert result.status is ValidationStatus.PASSED_WITH_WARNINGS
        assert result.decision.action is DecisionAction.PUBLISH_WITH_WARNINGS
        assert result.decision.publish_allowed is True

    def test_status_failed_on_blocking_findings(self):
        result = _engine([
            field_rule(passes=False, severity=Severity.BLOCKING, message="bad"),
        ]).validate(_request())
        assert result.status is ValidationStatus.FAILED
        assert result.decision.publish_allowed is False
        assert result.decision.action is DecisionAction.ROUTE_TO_EXCEPTION


class TestRuleErrorsAreNotFindings:
    def test_rule_execution_error_captured_as_validation_error(self):
        result = _engine([_ExplodingRule()]).validate(_request())

        assert len(result.errors) == 1
        assert isinstance(result.errors[0], ValidationError)
        assert result.errors[0].rule_id == "r.boom"
        assert "kaboom" in result.errors[0].message

        boom = next(r for r in result.rule_results if r.rule_id == "r.boom")
        assert boom.status is RuleExecutionStatus.ERROR
        assert boom.error is not None

        for f in result.findings:
            assert f.rule_id != "r.boom"

        assert result.status is ValidationStatus.ERROR
        assert result.decision.action in (DecisionAction.HALT, DecisionAction.ROUTE_TO_EXCEPTION)


class TestSummaryAggregates:
    def test_counts_match_findings(self):
        rules = [
            field_rule(rule_id="r.ok", passes=True, message="ok"),
            field_rule(rule_id="r.bad", passes=False, severity=Severity.BLOCKING, message="bad"),
            entity_rule(rule_id="r.warn", passes=False, severity=Severity.WARNING, message="warn"),
        ]
        result = _engine(rules).validate(_request())
        s = result.summary
        assert s.passed_count + s.failed_count == s.total_findings
        assert s.blocking_count >= 1
        assert s.warning_count >= 1
        assert s.total_entities_evaluated == 2

    def test_skipped_rules_excluded_from_total_rules_evaluated(self):
        # applies_to that doesn't match the request's entity_type -> SKIPPED
        rule = field_rule(
            rule_id="r.skip", passes=True, applies_to={"different_type"},
        )
        result = _engine([rule]).validate(_request())
        assert result.summary.total_rules_evaluated == 0
        assert result.summary.skipped_count == 1


class TestDeterministicTriggeredBy:
    def test_blocking_triggered_by_preserves_order(self):
        rules = [
            field_rule(rule_id="r.a", passes=False, severity=Severity.BLOCKING, message="a"),
            field_rule(rule_id="r.b", passes=False, severity=Severity.BLOCKING, message="b"),
            field_rule(rule_id="r.c", passes=False, severity=Severity.BLOCKING, message="c"),
        ]
        result = _engine(rules).validate(_request())
        # Order should be the order in which the failing rules first emitted findings.
        # r.a fires first on entity e1, then r.b, then r.c.
        assert result.decision.triggered_by[:3] == ("r.a", "r.b", "r.c")


class TestAppliesToDefense:
    """Engine must not substring-match a string ``applies_to`` to ``entity_type``."""

    def test_string_applies_to_does_not_substring_match(self):
        # A common mis-declaration: applies_to as a bare string instead of a set.
        rule = field_rule(rule_id="r.x", passes=True)
        rule.applies_to = "alphabet"  # type: ignore[assignment]

        # entity_type "alpha" is a substring of "alphabet" but should NOT match.
        result = _engine([rule]).validate(ValidationRequest(
            entity_type="alpha", ruleset_id="rs1",
            payload={"entities": [{"fields": {"x": 1}}]},
        ))
        skipped = [r for r in result.rule_results if r.rule_id == "r.x"]
        assert skipped[0].status is RuleExecutionStatus.SKIPPED

    def test_string_applies_to_exact_match_still_works(self):
        rule = field_rule(rule_id="r.y", passes=True)
        rule.applies_to = "alphabet"  # type: ignore[assignment]
        result = _engine([rule]).validate(ValidationRequest(
            entity_type="alphabet", ruleset_id="rs1",
            payload={"entities": [{"fields": {"x": 1}}]},
        ))
        run = [r for r in result.rule_results if r.rule_id == "r.y"]
        assert run[0].status is RuleExecutionStatus.PASSED


class TestRuleReturnTypeStrict:
    def test_non_finding_return_captured_as_error(self):
        class BadRule(Rule):
            rule_id = "r.bad"
            rule_version = "1.0"
            scope = Scope.ENTITY
            severity = Severity.BLOCKING
            category = Category.STRUCTURAL
            field_path = "*"
            applies_to = frozenset({"*"})
            def evaluate(self, target, ctx):
                return "this is wrong"  # not a Finding

        result = _engine([BadRule()]).validate(_request())
        assert result.status is ValidationStatus.ERROR
        assert len(result.errors) == 1
        assert "non-Finding" in result.errors[0].message

    def test_mixed_iterable_return_captured_as_error(self):
        class MixedRule(Rule):
            rule_id = "r.mixed"
            rule_version = "1.0"
            scope = Scope.ENTITY
            severity = Severity.BLOCKING
            category = Category.STRUCTURAL
            field_path = "*"
            applies_to = frozenset({"*"})
            def evaluate(self, target, ctx):
                return [self.make_finding(passed=True, message="ok"), "junk"]

        result = _engine([MixedRule()]).validate(_request())
        assert result.status is ValidationStatus.ERROR
        assert "non-Finding item" in result.errors[0].message


class TestRegistryMode:
    def test_from_registries_resolves_strategy_by_id(self):
        from validation_engine import RuleRegistry, StrategyRegistry

        rule_reg = RuleRegistry()
        rule_reg.register("record", "rs1", [field_rule(passes=True)])

        strat_reg = StrategyRegistry()
        strat_reg.register(SeverityGateStrategy(publish_target="t.publish"))

        engine = ValidationEngine.from_registries(
            rule_registry=rule_reg, strategy_registry=strat_reg,
        )
        result = engine.validate(_request(), strategy_id="severity_gate")
        assert result.decision.target == "t.publish"
        assert result.status is ValidationStatus.PASSED

    def test_from_registries_unknown_ruleset_raises(self):
        from validation_engine import RuleRegistry, StrategyRegistry
        engine = ValidationEngine.from_registries(
            rule_registry=RuleRegistry(),
            strategy_registry=StrategyRegistry(),
        )
        with pytest.raises(KeyError):
            engine.validate(_request(), strategy_id="severity_gate")

    def test_from_registries_without_strategy_id_raises(self):
        from validation_engine import RuleRegistry, StrategyRegistry
        rule_reg = RuleRegistry()
        rule_reg.register("record", "rs1", [field_rule(passes=True)])
        strat_reg = StrategyRegistry()
        strat_reg.register(SeverityGateStrategy())

        engine = ValidationEngine.from_registries(
            rule_registry=rule_reg, strategy_registry=strat_reg,
        )
        # Forgetting strategy_id when registry is configured is a misconfiguration.
        with pytest.raises(ValueError):
            engine.validate(_request())

    def test_strategy_id_without_registry_raises(self):
        engine = ValidationEngine(
            rules=[field_rule(passes=True)], strategy=SeverityGateStrategy(),
        )
        # Passing strategy_id without a registry is a misconfiguration.
        with pytest.raises(ValueError):
            engine.validate(_request(), strategy_id="severity_gate")
