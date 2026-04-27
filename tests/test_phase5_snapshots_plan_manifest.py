"""
Phase 5 tests:
  - ContractSnapshot model
  - ReferenceDataSnapshot wired into engine via ValidationRequest
  - ThresholdPolicy classification (Decimal-stable)
  - engine.plan() returns a ValidationPlan describing the run
  - Engine emits a ValidationManifest with deterministic hashes
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from validation_engine import (
    ContractFieldSnapshot,
    ContractSnapshot,
    ReferenceDataSnapshot,
    Severity,
    SeverityGateStrategy,
    ThresholdBand,
    ThresholdOperator,
    ThresholdPolicy,
    ValidationEngine,
    ValidationManifest,
    ValidationPlan,
    ValidationRequest,
)
from validation_engine.config.factory import RuleFactory
from validation_engine.config.schema import RuleConfig
from validation_engine.testing import field_rule


def _engine(rules):
    return ValidationEngine(rules=rules, strategy=SeverityGateStrategy())


def _request(entities, **kwargs):
    return ValidationRequest(
        entity_type="record", ruleset_id="rs1",
        payload={"entities": entities},
        **kwargs,
    )


# ─── ContractSnapshot ──────────────────────────────────────────────────────


class TestContractSnapshot:
    def test_minimal(self):
        c = ContractSnapshot(
            contract_id="acct.position", contract_version="v3",
            entity_type="position",
            fields=(
                ContractFieldSnapshot("account_id", "string", required=True),
                ContractFieldSnapshot("market_value", "decimal", required=True),
            ),
        )
        assert c.contract_id == "acct.position"
        assert len(c.fields) == 2

    def test_required_fields_validated(self):
        with pytest.raises(ValueError):
            ContractSnapshot(contract_id="", contract_version="v1", entity_type="x")
        with pytest.raises(ValueError):
            ContractSnapshot(contract_id="x", contract_version="v1", entity_type="")


# ─── ReferenceDataSnapshot ─────────────────────────────────────────────────


class TestReferenceDataSnapshotWiring:
    def test_snapshots_visible_to_rules(self):
        # A rule reads the snapshot via ctx.get_reference_data — so just
        # set a snapshot, run any rule, and confirm the engine merged it.
        # Simplest verification: the snapshot data ends up addressable from
        # a custom rule.
        from validation_engine.core.context import EvaluationContext
        from validation_engine.models.rule_evaluation import RuleEvaluation
        from validation_engine.rules.base import Rule
        from validation_engine.models.enums import Category, Scope, Severity

        class _LookupRule(Rule):
            rule_id = "r.lookup"
            scope = Scope.FIELD
            severity = Severity.BLOCKING
            category = Category.REFERENTIAL
            field_path = "ccy"
            applies_to = frozenset({"*"})

            def evaluate(self, ctx: EvaluationContext) -> RuleEvaluation:
                allowed = ctx.get_reference_data("iso_currencies", default=[])
                if ctx.field_value in allowed:
                    return self.passed()
                return self.failed(self.make_finding(
                    passed=False,
                    message=f"{ctx.field_value!r} not allowed",
                    actual=ctx.field_value,
                ))

        snapshot = ReferenceDataSnapshot(
            name="iso_currencies",
            data=["USD", "GBP", "JPY"],
        )
        engine = _engine([_LookupRule()])
        result = engine.validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [
                {"entity_ref": {"id": "1"}, "fields": {"ccy": "USD"}},
                {"entity_ref": {"id": "2"}, "fields": {"ccy": "ZZZ"}},
            ]},
            reference_data_snapshots={"iso_currencies": snapshot},
        ))
        assert result.summary.failed_count == 1


# ─── ThresholdPolicy ───────────────────────────────────────────────────────


class TestThresholdPolicy:
    def test_classify_picks_most_severe_match(self):
        policy = ThresholdPolicy(
            policy_id="nav_recon", metric_name="nav_diff", unit="USD",
            bands=(
                ThresholdBand(Severity.WARNING, ThresholdOperator.GT, Decimal("0.01")),
                ThresholdBand(Severity.BLOCKING, ThresholdOperator.GT, Decimal("1.00")),
                ThresholdBand(Severity.FATAL, ThresholdOperator.GT, Decimal("1000")),
            ),
        )
        assert policy.classify(Decimal("0.005")) is None
        assert policy.classify(Decimal("0.50")) is Severity.WARNING
        assert policy.classify(Decimal("5.00")) is Severity.BLOCKING
        assert policy.classify(Decimal("5000")) is Severity.FATAL

    def test_decimal_stable(self):
        # Float would round 0.1 + 0.2 -> 0.30000000000000004 and trip the
        # warning band. Decimal should keep the metric in the no-band area.
        policy = ThresholdPolicy(
            policy_id="p", metric_name="m",
            bands=(ThresholdBand(Severity.WARNING, ThresholdOperator.GT, Decimal("0.3")),),
        )
        assert policy.classify(Decimal("0.1") + Decimal("0.2")) is None

    def test_at_least_one_band_required(self):
        with pytest.raises(ValueError):
            ThresholdPolicy(policy_id="p", metric_name="m", bands=())


# ─── engine.plan() ─────────────────────────────────────────────────────────


class TestEnginePlan:
    def test_plan_lists_rules_without_running(self):
        rules = [
            field_rule(rule_id="r.a", passes=True),
            field_rule(rule_id="r.b", passes=False, severity=Severity.WARNING),
        ]
        engine = _engine(rules)
        plan = engine.plan(_request([{"entity_ref": {"id": "1"}, "fields": {"x": 1}}]))
        assert isinstance(plan, ValidationPlan)
        assert {p.rule_id for p in plan.planned_rules} == {"r.a", "r.b"}

    def test_plan_includes_dependencies(self):
        rule = RuleFactory().build(RuleConfig(
            rule_id="r.dep", rule_type="required", field_path="x",
        ))
        engine = _engine([rule])
        plan = engine.plan(_request([{"entity_ref": {"id": "1"}, "fields": {"x": 1}}]))
        # No deps -> empty tuple but still a tuple.
        planned = next(p for p in plan.planned_rules if p.rule_id == "r.dep")
        assert planned.dependencies == ()

    def test_plan_does_not_emit_findings(self):
        # Plan must not call evaluate() on any rule. Use a rule that would
        # explode if called to prove that.
        from validation_engine.core.context import EvaluationContext
        from validation_engine.rules.base import Rule
        from validation_engine.models.enums import Category, Scope, Severity

        class _Boom(Rule):
            rule_id = "r.boom"
            scope = Scope.FIELD
            severity = Severity.BLOCKING
            category = Category.STRUCTURAL
            field_path = "*"
            applies_to = frozenset({"*"})

            def evaluate(self, target, ctx: EvaluationContext):
                raise AssertionError("plan() must not call evaluate()")

        engine = _engine([_Boom()])
        plan = engine.plan(_request([{"entity_ref": {"id": "1"}, "fields": {"x": 1}}]))
        assert any(p.rule_id == "r.boom" for p in plan.planned_rules)


# ─── ValidationManifest ────────────────────────────────────────────────────


class TestValidationManifest:
    def test_engine_emits_manifest(self):
        engine = _engine([field_rule(passes=True)])
        result = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {"x": 1}},
        ]))
        assert isinstance(result.manifest, ValidationManifest)
        # Hashes are hex SHA-256 strings.
        assert len(result.manifest.payload_hash) == 64
        assert len(result.manifest.ruleset_hash) == 64

    def test_payload_hash_deterministic_across_runs(self):
        engine = _engine([field_rule(passes=True)])
        # Same payload, same ruleset — same payload_hash even if the runs
        # generated different request_ids.
        h1 = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {"x": 1}},
        ])).manifest.payload_hash
        h2 = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {"x": 1}},
        ])).manifest.payload_hash
        assert h1 == h2

    def test_payload_hash_changes_when_payload_changes(self):
        engine = _engine([field_rule(passes=True)])
        h1 = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {"x": 1}},
        ])).manifest.payload_hash
        h2 = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {"x": 2}},
        ])).manifest.payload_hash
        assert h1 != h2

    def test_manifest_includes_reference_snapshot_hashes(self):
        engine = _engine([field_rule(passes=True)])
        snapshot = ReferenceDataSnapshot(
            name="iso_currencies",
            data=["USD"],
            version="2026-04",
        )
        result = engine.validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [{"entity_ref": {"id": "1"}, "fields": {"x": 1}}]},
            reference_data_snapshots={"iso_currencies": snapshot},
        ))
        assert "iso_currencies" in result.manifest.reference_data_hashes
        assert len(result.manifest.reference_data_hashes["iso_currencies"]) == 64

    def test_manifest_includes_contract_hash(self):
        engine = _engine([field_rule(passes=True)])
        contract = ContractSnapshot(
            contract_id="c", contract_version="v1", entity_type="record",
            fields=(ContractFieldSnapshot("x", "integer", required=True),),
        )
        result = engine.validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [{"entity_ref": {"id": "1"}, "fields": {"x": 1}}]},
            contract_snapshot=contract,
        ))
        assert result.manifest.contract_snapshot_hash is not None
        assert len(result.manifest.contract_snapshot_hash) == 64

    def test_engine_version_recorded(self):
        engine = _engine([field_rule(passes=True)])
        result = engine.validate(_request([
            {"entity_ref": {"id": "1"}, "fields": {"x": 1}},
        ]))
        assert result.manifest.engine_version is not None
        assert result.manifest.python_version is not None
