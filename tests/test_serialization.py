"""Round-trip tests for to_jsonable/from_jsonable on real public models."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from validation_engine import (
    Category,
    DecisionAction,
    RuleExecutionStatus,
    Scope,
    Severity,
    ValidationDecision,
    ValidationError,
    ValidationFinding,
    ValidationRequest,
    ValidationStatus,
    ValidationSummary,
)
from validation_engine.core.serialization import (
    from_json,
    from_jsonable,
    to_json,
    to_jsonable,
)


class TestPrimitives:
    def test_none_and_scalars_pass_through(self):
        for v in [None, True, 1, 1.5, "hi"]:
            assert to_jsonable(v) == v

    def test_decimal_serializes_as_string(self):
        assert to_jsonable(Decimal("1.50")) == "1.50"

    def test_decimal_round_trip(self):
        d = Decimal("3.14159")
        assert from_jsonable(Decimal, to_jsonable(d)) == d

    def test_datetime_round_trip(self):
        dt = datetime(2026, 4, 26, 12, 30, 0, tzinfo=timezone.utc)
        assert from_jsonable(datetime, to_jsonable(dt)) == dt

    def test_enum_round_trip(self):
        assert from_jsonable(Severity, to_jsonable(Severity.WARNING)) is Severity.WARNING

    def test_non_finite_float_rejected(self):
        with pytest.raises(ValueError):
            to_jsonable(float("nan"))


class TestValidationFindingRoundTrip:
    def test_basic_finding_round_trips(self):
        f = ValidationFinding(
            rule_id="r.x",
            severity=Severity.BLOCKING,
            category=Category.STRUCTURAL,
            passed=False,
            message="bad value",
            field_path="amount",
            expected="numeric",
            actual="oops",
            entity_ref={"id": "e1"},
            evidence={"snippet": "..."},
            involved_fields=("amount",),
        )
        encoded = to_jsonable(f)
        # Should be a plain dict — JSON-friendly.
        json.dumps(encoded)
        revived = from_jsonable(ValidationFinding, encoded)
        assert revived.rule_id == f.rule_id
        assert revived.severity is Severity.BLOCKING
        assert revived.category is Category.STRUCTURAL
        assert revived.passed is False
        assert revived.message == f.message
        assert revived.field_path == "amount"
        assert revived.expected == "numeric"
        assert dict(revived.entity_ref) == {"id": "e1"}
        assert dict(revived.evidence) == {"snippet": "..."}
        assert revived.involved_fields == ("amount",)


class TestValidationDecisionRoundTrip:
    def test_decision_round_trip(self):
        d = ValidationDecision.publish(target="topic.publish")
        revived = from_jsonable(ValidationDecision, to_jsonable(d))
        assert revived.action is DecisionAction.PUBLISH
        assert revived.target == "topic.publish"
        assert revived.publish_allowed is True


class TestValidationErrorRoundTrip:
    def test_error_round_trip_preserves_fields(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            err = ValidationError.from_exception(
                exc, rule_id="r.x", rule_version="1.0", context={"k": "v"},
            )
        revived = from_jsonable(ValidationError, to_jsonable(err))
        assert revived.error_type == "RuntimeError"
        assert "boom" in revived.message
        assert revived.rule_id == "r.x"
        assert dict(revived.context) == {"k": "v"}


class TestValidationSummaryRoundTrip:
    def test_summary_round_trip(self):
        s = ValidationSummary(
            total_rules_evaluated=2, total_entities_evaluated=3,
            total_findings=4, passed_count=2, failed_count=2,
            warning_count=1, blocking_count=1, error_count=0,
            skipped_count=0, pass_rate=0.5,
        )
        revived = from_jsonable(ValidationSummary, to_jsonable(s))
        assert revived == s


class TestValidationRequestRoundTrip:
    def test_request_round_trip(self):
        req = ValidationRequest(
            entity_type="record",
            ruleset_id="rs1",
            ruleset_version="v2",
            payload={"entities": [{"fields": {"x": 1}}]},
            metadata={"tenant": "abc"},
        )
        revived = from_jsonable(ValidationRequest, to_jsonable(req))
        assert revived.entity_type == req.entity_type
        assert revived.ruleset_id == req.ruleset_id
        assert revived.ruleset_version == "v2"
        assert revived.payload == req.payload
        assert dict(revived.metadata) == {"tenant": "abc"}


class TestJsonHelpers:
    def test_to_json_then_from_json(self):
        f = ValidationFinding(
            rule_id="r", severity=Severity.WARNING, category=Category.BUSINESS,
            passed=True, message="ok",
        )
        raw = to_json(f)
        revived = from_json(ValidationFinding, raw)
        assert revived.rule_id == "r"
        assert revived.severity is Severity.WARNING


class TestExecutionStatusEnum:
    def test_rule_execution_status_round_trip(self):
        for s in RuleExecutionStatus:
            assert from_jsonable(RuleExecutionStatus, to_jsonable(s)) is s

    def test_validation_status_round_trip(self):
        for s in ValidationStatus:
            assert from_jsonable(ValidationStatus, to_jsonable(s)) is s

    def test_scope_round_trip(self):
        for s in Scope:
            assert from_jsonable(Scope, to_jsonable(s)) is s
