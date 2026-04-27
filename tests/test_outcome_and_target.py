"""Tests for ValidationOutcome, ValidationTarget, Observation, RuleEvaluation."""
from __future__ import annotations

import pytest

from validation_engine import (
    Category,
    Observation,
    RuleEvaluation,
    RuleEvaluationStatus,
    Scope,
    Severity,
    SeverityGateStrategy,
    ValidationDecision,
    ValidationEngine,
    ValidationFinding,
    ValidationOutcome,
    ValidationRequest,
    ValidationStatus,
    ValidationTarget,
    finding_codes,
)
from validation_engine.core.serialization import from_jsonable, to_jsonable
from validation_engine.testing import field_rule


# ─── ValidationOutcome ──────────────────────────────────────────────────────


class TestValidationOutcomeFactory:
    def test_clean(self):
        o = ValidationOutcome.from_signals(
            warning_count=0, blocking_count=0, error_count=0,
        )
        assert o.status is ValidationStatus.PASSED
        assert o.is_valid is True
        assert o.has_warnings is False
        assert o.has_blocking_findings is False
        assert o.has_errors is False

    def test_warnings_only(self):
        o = ValidationOutcome.from_signals(
            warning_count=2, blocking_count=0, error_count=0,
        )
        assert o.status is ValidationStatus.PASSED_WITH_WARNINGS
        assert o.is_valid is True
        assert o.has_warnings is True

    def test_blocking_dominates_warning(self):
        o = ValidationOutcome.from_signals(
            warning_count=2, blocking_count=1, error_count=0,
        )
        assert o.status is ValidationStatus.FAILED_BLOCKING
        assert o.is_valid is False
        assert o.has_blocking_findings is True
        assert o.has_warnings is True

    def test_error_dominates_blocking(self):
        o = ValidationOutcome.from_signals(
            warning_count=0, blocking_count=3, error_count=1,
        )
        assert o.status is ValidationStatus.ERROR
        assert o.is_valid is False
        assert o.has_errors is True
        assert o.has_blocking_findings is True

    def test_invalid_input_dominates_everything(self):
        o = ValidationOutcome.from_signals(
            warning_count=10, blocking_count=10, error_count=10,
            invalid_input=True,
        )
        assert o.status is ValidationStatus.INVALID_INPUT
        assert o.is_valid is False


class TestValidationOutcomeMentionsNoRouting:
    def test_no_publish_quarantine_mention(self):
        # The whole point of ValidationOutcome is to live without
        # publish/quarantine vocabulary. Any rationale string we autogenerate
        # should stay validation-flavoured.
        for o in [
            ValidationOutcome.from_signals(warning_count=0, blocking_count=0, error_count=0),
            ValidationOutcome.from_signals(warning_count=2, blocking_count=0, error_count=0),
            ValidationOutcome.from_signals(warning_count=0, blocking_count=2, error_count=0),
            ValidationOutcome.from_signals(warning_count=0, blocking_count=0, error_count=2),
        ]:
            for line in o.rationale:
                assert "publish" not in line.lower() or "publish allowed" in line.lower()
                assert "quarantine" not in line.lower()
                assert "ticket" not in line.lower()


# ─── ValidationTarget ───────────────────────────────────────────────────────


class TestValidationTarget:
    def test_field_target(self):
        t = ValidationTarget.field("amount")
        assert t.scope is Scope.FIELD
        assert t.field_path == "amount"

    def test_relationship_target_requires_two_fields(self):
        with pytest.raises(ValueError):
            ValidationTarget(scope=Scope.RELATIONSHIP, relationship_fields=("only_one",))

    def test_group_target_requires_group_by(self):
        with pytest.raises(ValueError):
            ValidationTarget(scope=Scope.GROUP)

    def test_relationship_factory(self):
        t = ValidationTarget.relationship("issue_date", "maturity_date")
        assert t.scope is Scope.RELATIONSHIP
        assert t.relationship_fields == ("issue_date", "maturity_date")

    def test_group_factory(self):
        t = ValidationTarget.group("entity_ref.account_id")
        assert t.scope is Scope.GROUP
        assert t.group_by == ("entity_ref.account_id",)

    def test_round_trip(self):
        t = ValidationTarget.relationship("a", "b")
        revived = from_jsonable(ValidationTarget, to_jsonable(t))
        assert revived.scope is Scope.RELATIONSHIP
        assert revived.relationship_fields == ("a", "b")


# ─── Observation ────────────────────────────────────────────────────────────


class TestObservation:
    def test_minimal(self):
        o = Observation(rule_id="r.x", metric_name="record_count", value=10)
        assert o.metric_name == "record_count"
        assert o.value == 10
        assert o.observation_id.startswith("obs_")

    def test_round_trip(self):
        o = Observation(
            rule_id="r.x",
            metric_name="completeness_ratio",
            value="0.997",
            unit="ratio",
            field_path="fusion_id",
            dimensions={"group": "A"},
        )
        revived = from_jsonable(Observation, to_jsonable(o))
        assert revived.metric_name == "completeness_ratio"
        assert revived.unit == "ratio"
        assert dict(revived.dimensions) == {"group": "A"}


# ─── RuleEvaluation ────────────────────────────────────────────────────────


class TestRuleEvaluation:
    def test_passed_factory(self):
        ev = RuleEvaluation.passed()
        assert ev.status is RuleEvaluationStatus.PASSED
        assert ev.findings == ()

    def test_failed_factory(self):
        f = ValidationFinding(
            rule_id="r", severity=Severity.BLOCKING, category=Category.STRUCTURAL,
            passed=False, message="bad",
        )
        ev = RuleEvaluation.failed([f])
        assert ev.status is RuleEvaluationStatus.FAILED
        assert ev.findings == (f,)

    def test_failed_requires_findings(self):
        with pytest.raises(ValueError):
            RuleEvaluation.failed([])

    def test_not_applicable_factory(self):
        ev = RuleEvaluation.not_applicable("instrument_type != bond")
        assert ev.status is RuleEvaluationStatus.NOT_APPLICABLE
        assert ev.metadata["reason"] == "instrument_type != bond"

    def test_passed_can_carry_observations(self):
        obs = Observation(rule_id="r", metric_name="record_count", value=42)
        ev = RuleEvaluation.passed(observations=[obs])
        assert len(ev.observations) == 1


# ─── ValidationFinding finding_code & target ───────────────────────────────


class TestFindingExtensions:
    def test_finding_code_optional_default_empty(self):
        f = ValidationFinding(
            rule_id="r", severity=Severity.BLOCKING, category=Category.STRUCTURAL,
            passed=False, message="x",
        )
        assert f.finding_code == ""
        assert f.target is None
        assert f.observation_ids == ()

    def test_finding_code_populates_when_provided(self):
        f = ValidationFinding(
            rule_id="r", severity=Severity.BLOCKING, category=Category.STRUCTURAL,
            passed=False, message="missing",
            finding_code=finding_codes.REQUIRED_FIELD_MISSING,
            target=ValidationTarget.field("amount"),
            observation_ids=("obs_a", "obs_b"),
        )
        assert f.finding_code == "REQUIRED_FIELD_MISSING"
        assert f.target.field_path == "amount"
        assert f.observation_ids == ("obs_a", "obs_b")


# ─── ValidationResult.outcome wired by engine ──────────────────────────────


class TestEngineProducesOutcome:
    def _engine(self, rules):
        return ValidationEngine(rules=rules, strategy=SeverityGateStrategy())

    def _request(self):
        return ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [{"entity_ref": {"id": "e1"}, "fields": {"x": 1}}]},
        )

    def test_passed_outcome(self):
        result = self._engine([field_rule(passes=True)]).validate(self._request())
        assert result.outcome is not None
        assert result.outcome.status is ValidationStatus.PASSED
        assert result.outcome.is_valid is True

    def test_warning_outcome(self):
        result = self._engine([
            field_rule(passes=False, severity=Severity.WARNING, message="warn"),
        ]).validate(self._request())
        assert result.outcome.status is ValidationStatus.PASSED_WITH_WARNINGS
        assert result.outcome.is_valid is True

    def test_blocking_outcome(self):
        result = self._engine([
            field_rule(passes=False, severity=Severity.BLOCKING, message="bad"),
        ]).validate(self._request())
        assert result.outcome.status is ValidationStatus.FAILED_BLOCKING
        assert result.outcome.is_valid is False
        assert result.outcome.has_blocking_findings is True


# ─── Severity.ERROR is treated as blocking by gate ─────────────────────────


class TestSeverityErrorBlocks:
    def test_error_severity_blocks_publication(self):
        engine = ValidationEngine(
            rules=[field_rule(
                passes=False, severity=Severity.ERROR, message="error finding",
            )],
            strategy=SeverityGateStrategy(),
        )
        result = engine.validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [{"entity_ref": {"id": "e1"}, "fields": {"x": 1}}]},
        ))
        # ERROR-severity findings must be treated like BLOCKING by the
        # default gate strategy: they prevent publication.
        assert result.decision.publish_allowed is False
        assert result.outcome.status is ValidationStatus.FAILED_BLOCKING
        assert result.summary.blocking_count == 1
