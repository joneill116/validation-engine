"""
End-to-end tests covering all three built-in strategies.

Two entities:
  - apple  → all fields clean
  - bad_co → country_of_risk fails (BLOCKING), issuer/lei cross-field warning
"""
import pytest
from validation_engine import (
    ValidationEngine,
    Severity, Scope, Category,
    ActionType, Disposition,
    SeverityGateStrategy,
    FieldPartitionStrategy,
    StrictStrategy,
    make_finding,
)
from validation_engine.engine.context import EvaluationContext
from validation_engine.testing import field_rule, entity_rule, collection_rule


# ── Sample rules ──────────────────────────────────────────────────────────────

VALID_COUNTRIES = {"US", "GB", "DE", "JP", "FR"}


class CountryCodeRule:
    rule_id = "country_in_allowed_set"
    scope = Scope.FIELD
    severity = Severity.BLOCKING
    category = Category.STRUCTURAL
    field_path = "country_of_risk"
    applies_to = {"*"}

    def evaluate(self, target, ctx: EvaluationContext):
        passed = target in VALID_COUNTRIES
        return make_finding(
            self, passed,
            message=f"{target!r} is not a valid country code" if not passed else "OK",
            field_path=self.field_path,
            expected=f"one of {sorted(VALID_COUNTRIES)}",
            actual=target,
        )


class LeiRequiredForEquityRule:
    rule_id = "lei_required_for_equity"
    scope = Scope.FIELD
    severity = Severity.BLOCKING
    category = Category.COMPLETENESS
    field_path = "lei"
    applies_to = {"instrument"}

    def evaluate(self, target, ctx: EvaluationContext):
        passed = target is not None and target != ""
        return make_finding(
            self, passed,
            message="LEI is required for equity instruments" if not passed else "OK",
            field_path=self.field_path,
            actual=target,
        )


class IssuerLeiConsistencyRule:
    rule_id = "issuer_lei_consistency"
    scope = Scope.ENTITY
    severity = Severity.WARNING
    category = Category.CONSISTENCY
    field_path = "*"
    applies_to = {"instrument"}

    def evaluate(self, target, ctx: EvaluationContext):
        fields = target.get("fields", {})
        issuer = fields.get("issuer_name", {})
        lei = fields.get("lei", {})
        issuer_val = issuer.get("value") if isinstance(issuer, dict) else issuer
        lei_val = lei.get("value") if isinstance(lei, dict) else lei
        # synthetic check: if issuer is present but lei is None/empty → warning
        passed = not (issuer_val and not lei_val)
        return make_finding(
            self, passed,
            message="Issuer present but LEI missing — cannot verify entity identity",
            involved_fields=("issuer_name", "lei"),
        )


RULES = [CountryCodeRule(), LeiRequiredForEquityRule(), IssuerLeiConsistencyRule()]

# ── Sample payload ────────────────────────────────────────────────────────────

PAYLOAD = {
    "entities": [
        {
            "entity_ref": {"subject_ref_id": "ref_apple", "spine_id": "spine_001", "natural_keys": {"isin": "US0378331005"}},
            "fields": {
                "issuer_name":     {"value": "Apple Inc.",  "source_system": "BLOOMBERG", "signal_id": "sig_001"},
                "cusip":           {"value": "037833100",   "source_system": "RIMES",     "signal_id": "sig_002"},
                "country_of_risk": {"value": "US",          "source_system": "BLOOMBERG", "signal_id": "sig_003"},
                "lei":             {"value": "HWUPKR0MPOU8FGXBT394", "source_system": "GLEIF", "signal_id": "sig_004"},
            },
        },
        {
            "entity_ref": {"subject_ref_id": "ref_badco", "spine_id": "spine_002", "natural_keys": {"isin": "XX9999999999"}},
            "fields": {
                "issuer_name":     {"value": "Bad Co.",   "source_system": "BLOOMBERG", "signal_id": "sig_010"},
                "cusip":           {"value": "999999999", "source_system": "RIMES",     "signal_id": "sig_011"},
                "country_of_risk": {"value": "XX",        "source_system": "BLOOMBERG", "signal_id": "sig_012"},
                "lei":             {"value": None,        "source_system": "GLEIF",     "signal_id": "sig_013"},
            },
        },
    ]
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_engine(strategy):
    return ValidationEngine(rules=RULES, strategy=strategy)


# ── SeverityGateStrategy ──────────────────────────────────────────────────────

class TestSeverityGate:
    def setup_method(self):
        self.engine = make_engine(
            SeverityGateStrategy(
                publish_target="topic.validated",
                exception_target="topic.exceptions",
            )
        )
        self.decision = self.engine.validate(
            payload=PAYLOAD,
            entity_type="instrument",
            ruleset_id="instrument:equity:standard",
        )

    def test_two_actions_produced(self):
        assert len(self.decision.actions) == 2

    def test_apple_is_published(self):
        publishes = self.decision.by_action_type(ActionType.PUBLISH)
        assert len(publishes) == 1
        assert publishes[0].entity_ref["subject_ref_id"] == "ref_apple"
        assert publishes[0].target == "topic.validated"

    def test_badco_raises_exception(self):
        exceptions = self.decision.by_action_type(ActionType.RAISE_EXCEPTION)
        assert len(exceptions) == 1
        assert exceptions[0].entity_ref["subject_ref_id"] == "ref_badco"
        assert exceptions[0].target == "topic.exceptions"

    def test_badco_payload_contains_failures(self):
        exc = self.decision.by_action_type(ActionType.RAISE_EXCEPTION)[0]
        assert len(exc.payload["failures"]) > 0


# ── FieldPartitionStrategy ────────────────────────────────────────────────────

class TestFieldPartition:
    def setup_method(self):
        self.engine = make_engine(
            FieldPartitionStrategy(
                publish_target="topic.validated",
                exception_target="topic.exceptions",
            )
        )
        self.decision = self.engine.validate(
            payload=PAYLOAD,
            entity_type="instrument",
            ruleset_id="instrument:equity:standard",
        )

    def test_three_actions_produced(self):
        # apple → 1 publish; bad_co → 1 publish (clean fields) + 1 exception (bad fields)
        assert len(self.decision.actions) == 3

    def test_apple_full_publish(self):
        publishes = [a for a in self.decision.by_action_type(ActionType.PUBLISH)
                     if a.entity_ref["subject_ref_id"] == "ref_apple"]
        assert len(publishes) == 1
        assert publishes[0].payload["partial"] is False

    def test_badco_partial_publish(self):
        publishes = [a for a in self.decision.by_action_type(ActionType.PUBLISH)
                     if a.entity_ref["subject_ref_id"] == "ref_badco"]
        assert len(publishes) == 1
        assert publishes[0].payload["partial"] is True
        # clean fields should not include the failing ones
        assert "country_of_risk" not in publishes[0].payload["fields"]
        assert "lei" not in publishes[0].payload["fields"]

    def test_badco_exception_contains_bad_fields(self):
        exceptions = self.decision.by_action_type(ActionType.RAISE_EXCEPTION)
        assert len(exceptions) == 1
        assert "country_of_risk" in exceptions[0].payload["failed_fields"]
        assert "lei" in exceptions[0].payload["failed_fields"]


# ── StrictStrategy ────────────────────────────────────────────────────────────

class TestStrict:
    def setup_method(self):
        self.engine = make_engine(
            StrictStrategy(
                publish_target="topic.validated",
                hold_target="topic.held",
            )
        )
        self.decision = self.engine.validate(
            payload=PAYLOAD,
            entity_type="instrument",
            ruleset_id="instrument:equity:standard",
        )

    def test_all_held_when_any_failure(self):
        holds = self.decision.by_action_type(ActionType.HOLD)
        assert len(holds) == 2  # both entities held

    def test_batch_exception_raised(self):
        exceptions = self.decision.by_action_type(ActionType.RAISE_EXCEPTION)
        assert len(exceptions) == 1
        assert exceptions[0].payload["failed_entities"] == 1  # only bad_co

    def test_summary_reflects_held(self):
        assert self.decision.summary["held"] == 2


# ── Clean batch → strict publishes all ───────────────────────────────────────

class TestStrictCleanBatch:
    def setup_method(self):
        self.engine = make_engine(
            StrictStrategy(publish_target="topic.validated", hold_target="topic.held")
        )
        clean_payload = {
            "entities": [
                {
                    "entity_ref": {"subject_ref_id": "ref_clean"},
                    "fields": {
                        "country_of_risk": {"value": "US"},
                        "lei": {"value": "HWUPKR0MPOU8FGXBT394"},
                        "issuer_name": {"value": "Clean Corp"},
                    },
                }
            ]
        }
        self.decision = self.engine.validate(
            payload=clean_payload,
            entity_type="instrument",
            ruleset_id="instrument:equity:standard",
        )

    def test_publishes_when_clean(self):
        assert len(self.decision.by_action_type(ActionType.PUBLISH)) == 1
        assert len(self.decision.by_action_type(ActionType.HOLD)) == 0


# ── Collection-level rule blocks entire batch ─────────────────────────────────

class TestCollectionRuleBlocking:
    def test_hold_all_on_collection_failure(self):
        engine = ValidationEngine(
            rules=[collection_rule(passes=False, message="duplicate natural key detected")],
            strategy=SeverityGateStrategy(
                publish_target="topic.validated",
                exception_target="topic.exceptions",
            ),
        )
        decision = engine.validate(
            payload=PAYLOAD,
            entity_type="instrument",
            ruleset_id="test",
        )
        holds = decision.by_action_type(ActionType.HOLD)
        assert len(holds) == 2
