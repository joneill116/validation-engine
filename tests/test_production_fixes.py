"""
Tests for the four production-readiness fixes:
  #1 ContractSnapshot now produces real findings
  #2a ValidationProfile is consumed by the engine (manifest + pre-flight)
  #2b ThresholdPolicy classifies sum_equals diffs and overrides severity
  #3 Group defaults no longer override explicit rule severity/category
  #4 finding_id and observation_id use full UUIDs
"""
from __future__ import annotations

import textwrap
import uuid
from decimal import Decimal

import pytest

from validation_engine import (
    Category,
    ConfigLoader,
    ContractFieldSnapshot,
    ContractSnapshot,
    ReferenceDataSnapshot,
    RuleConfig,
    RulesetCompiler,
    Severity,
    SeverityGateStrategy,
    StrategyConfig,
    ThresholdBand,
    ThresholdOperator,
    ThresholdPolicy,
    ValidationEngine,
    ValidationProfile,
    ValidationRequest,
    ValidationStatus,
    finding_codes,
)
from validation_engine.testing import field_rule


def _engine_from_cfg(cfg):
    compiled = RulesetCompiler().compile(cfg)
    return ValidationEngine(rules=list(compiled.rules), strategy=compiled.strategy)


def _ruleset(*rules):
    from validation_engine.config.schema import RulesetConfig
    return RulesetConfig(
        ruleset_id="rs1", ruleset_version="v1", entity_type="record",
        rules=tuple(rules),
        strategy=StrategyConfig(strategy_type="severity_gate"),
    )


# ─── Fix #4 — full UUIDs ───────────────────────────────────────────────────


class TestFix4FullUUIDs:
    def test_finding_id_is_full_uuid_hex(self):
        engine = ValidationEngine(
            rules=[field_rule(passes=False, severity=Severity.BLOCKING, message="x")],
            strategy=SeverityGateStrategy(),
        )
        result = engine.validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [{"entity_ref": {"id": "1"}, "fields": {"x": 1}}]},
        ))
        f = result.findings[0]
        assert f.finding_id.startswith("f_")
        # 32 hex chars after the prefix
        suffix = f.finding_id[2:]
        assert len(suffix) == 32
        # Sanity: it parses as a valid UUID
        uuid.UUID(suffix)


# ─── Fix #3 — group defaults respect explicit rule severity ────────────────


class TestFix3GroupDefaultsRespectExplicit:
    def _yaml(self, body: str):
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("PyYAML not installed")
        return ConfigLoader().loads(textwrap.dedent(body), fmt="yaml")

    def test_explicit_rule_severity_wins_over_group_default(self):
        cfg = self._yaml("""
            ruleset_id: rs1
            ruleset_version: v1
            entity_type: record
            rule_groups:
              - group_id: structural
                default_severity: blocking
                rules:
                  - rule_id: r.a
                    rule_type: required
                    field_path: x
                    severity: warning      # explicit override
                  - rule_id: r.b
                    rule_type: required
                    field_path: y          # no severity -> group default applies
        """)
        flat = {r.rule_id: r for r in cfg.rules}
        # Explicit warning kept.
        assert flat["r.a"].severity is Severity.WARNING
        # Defaulted rule picks up group's blocking.
        assert flat["r.b"].severity is Severity.BLOCKING

    def test_explicit_rule_category_wins_over_group_default(self):
        cfg = self._yaml("""
            ruleset_id: rs1
            ruleset_version: v1
            entity_type: record
            rule_groups:
              - group_id: g1
                default_category: completeness
                rules:
                  - rule_id: r.a
                    rule_type: required
                    field_path: x
                    category: business     # explicit
                  - rule_id: r.b
                    rule_type: required
                    field_path: y
        """)
        flat = {r.rule_id: r for r in cfg.rules}
        assert flat["r.a"].category is Category.BUSINESS
        assert flat["r.b"].category is Category.COMPLETENESS

    def test_factory_resolves_none_to_blocking_structural(self):
        # Direct programmatic construction with no severity/category set
        # at all — must still produce a runnable rule.
        cfg = _ruleset(RuleConfig(
            rule_id="r.x", rule_type="required", field_path="acct",
        ))
        engine = _engine_from_cfg(cfg)
        result = engine.validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [{"entity_ref": {"id": "1"}, "fields": {}}]},
        ))
        # Defaulted rule fired and produced a blocking finding.
        assert result.summary.blocking_count == 1


# ─── Fix #2a — ValidationProfile wiring ────────────────────────────────────


class TestFix2aProfileWiring:
    def _engine(self):
        return ValidationEngine(
            rules=[field_rule(passes=True)],
            strategy=SeverityGateStrategy(),
        )

    def test_profile_hash_in_manifest(self):
        profile = ValidationProfile(
            profile_id="acct.daily", profile_version="v1",
            ruleset_id="rs1",
        )
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [{"entity_ref": {"id": "1"}, "fields": {"x": 1}}]},
            profile=profile,
        ))
        assert result.manifest.profile_hash is not None
        assert len(result.manifest.profile_hash) == 64

    def test_no_profile_means_no_profile_hash(self):
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [{"entity_ref": {"id": "1"}, "fields": {"x": 1}}]},
        ))
        assert result.manifest.profile_hash is None

    def test_missing_required_reference_data_raises_validation_error(self):
        profile = ValidationProfile(
            profile_id="p", profile_version="v1",
            required_reference_data=("iso_currencies", "valid_accounts"),
        )
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [{"entity_ref": {"id": "1"}, "fields": {"x": 1}}]},
            profile=profile,
            # Only one of two supplied.
            reference_data_snapshots={
                "iso_currencies": ReferenceDataSnapshot(
                    name="iso_currencies", data=["USD"],
                ),
            },
        ))
        # One missing -> one error.
        types = [e.error_type for e in result.errors]
        assert "ProfileExpectationUnmet" in types
        # Outcome promoted to ERROR because of the runtime error.
        assert result.outcome.status is ValidationStatus.ERROR

    def test_contract_id_mismatch_raises_validation_error(self):
        profile = ValidationProfile(
            profile_id="p", profile_version="v1",
            expected_contract_id="acct.position",
            expected_contract_version="v3",
        )
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [{"entity_ref": {"id": "1"}, "fields": {"x": 1}}]},
            profile=profile,
            contract_snapshot=ContractSnapshot(
                contract_id="something.else", contract_version="v3",
                entity_type="record",
            ),
        ))
        msgs = " ".join(e.message for e in result.errors)
        assert "expects contract_id" in msgs

    def test_contract_version_mismatch_raises_validation_error(self):
        profile = ValidationProfile(
            profile_id="p", profile_version="v1",
            expected_contract_id="acct.position",
            expected_contract_version="v3",
        )
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [{"entity_ref": {"id": "1"}, "fields": {"x": 1}}]},
            profile=profile,
            contract_snapshot=ContractSnapshot(
                contract_id="acct.position", contract_version="v2",
                entity_type="record",
            ),
        ))
        msgs = " ".join(e.message for e in result.errors)
        assert "expects contract_version" in msgs

    def test_contract_supplied_when_required_but_missing(self):
        profile = ValidationProfile(
            profile_id="p", profile_version="v1",
            expected_contract_id="acct.position",
        )
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [{"entity_ref": {"id": "1"}, "fields": {"x": 1}}]},
            profile=profile,
            # No contract_snapshot
        ))
        msgs = " ".join(e.message for e in result.errors)
        assert "supplied no contract_snapshot" in msgs


# ─── Fix #2b — ThresholdPolicy + SumEqualsRule ─────────────────────────────


class TestFix2bThresholdPolicyOnSumEquals:
    def _build_engine_and_request(
        self, *, totals: list[Decimal], threshold_policy_id: str | None,
    ):
        params: dict = {
            "amount_field": "amt",
            "expected_value": "100",
        }
        if threshold_policy_id is not None:
            params["threshold_policy"] = threshold_policy_id
        cfg = _ruleset(RuleConfig(
            rule_id="r.recon",
            rule_type="sum_equals",
            scope=None,  # default collection scope
            severity=Severity.BLOCKING,
            params=params,
        ))
        engine = _engine_from_cfg(cfg)

        profile = ValidationProfile(
            profile_id="p", profile_version="v1",
            threshold_policies={
                "nav_recon": ThresholdPolicy(
                    policy_id="nav_recon",
                    metric_name="nav_diff",
                    bands=(
                        ThresholdBand(Severity.WARNING, ThresholdOperator.GT, Decimal("0.01")),
                        ThresholdBand(Severity.BLOCKING, ThresholdOperator.GT, Decimal("1.00")),
                        ThresholdBand(Severity.FATAL, ThresholdOperator.GT, Decimal("1000")),
                    ),
                ),
            },
        )
        request = ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [
                {"entity_ref": {"id": str(i)}, "fields": {"amt": str(t)}}
                for i, t in enumerate(totals)
            ]},
            profile=profile,
        )
        return engine, request

    def test_diff_inside_smallest_band_passes(self):
        engine, request = self._build_engine_and_request(
            totals=[Decimal("100.005")],     # diff 0.005 < 0.01
            threshold_policy_id="nav_recon",
        )
        result = engine.validate(request)
        assert result.outcome.is_valid is True
        assert result.summary.failed_count == 0

    def test_diff_in_warning_band_emits_warning(self):
        engine, request = self._build_engine_and_request(
            totals=[Decimal("100.50")],     # diff 0.50 -> warning band
            threshold_policy_id="nav_recon",
        )
        result = engine.validate(request)
        # The static rule severity is BLOCKING, but the band overrode it.
        assert any(
            f.severity is Severity.WARNING and not f.passed
            for f in result.findings
        )
        assert result.summary.warning_count == 1
        assert result.summary.blocking_count == 0

    def test_diff_in_blocking_band_emits_blocking(self):
        engine, request = self._build_engine_and_request(
            totals=[Decimal("105.00")],     # diff 5 -> blocking band
            threshold_policy_id="nav_recon",
        )
        result = engine.validate(request)
        assert result.summary.blocking_count == 1

    def test_diff_in_fatal_band_emits_fatal(self):
        engine, request = self._build_engine_and_request(
            totals=[Decimal("5000")],     # diff 4900 -> fatal band
            threshold_policy_id="nav_recon",
        )
        result = engine.validate(request)
        # FATAL counts as blocking-class for the gate.
        assert any(
            f.severity is Severity.FATAL and not f.passed
            for f in result.findings
        )

    def test_no_threshold_policy_falls_back_to_static_tolerance(self):
        engine, request = self._build_engine_and_request(
            totals=[Decimal("100.50")],
            threshold_policy_id=None,    # no policy -> flat tolerance default 0.01
        )
        result = engine.validate(request)
        # Diff > 0.01 -> static BLOCKING applies.
        assert result.summary.blocking_count == 1


# ─── Fix #1 — ContractSnapshot enforcement produces real findings ──────────


class TestFix1ContractEnforcement:
    def _engine(self):
        # No user rules — we want to see only contract rules firing.
        return ValidationEngine(rules=[], strategy=SeverityGateStrategy())

    def test_required_field_missing_emits_finding(self):
        contract = ContractSnapshot(
            contract_id="acct.position", contract_version="v1",
            entity_type="position",
            fields=(
                ContractFieldSnapshot("market_value", "decimal", required=True),
            ),
        )
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [
                {"entity_ref": {"id": "1"}, "fields": {}},
            ]},
            contract_snapshot=contract,
        ))
        codes = {f.finding_code for f in result.findings if not f.passed}
        assert finding_codes.CONTRACT_FIELD_MISSING in codes

    def test_present_field_satisfies_required(self):
        contract = ContractSnapshot(
            contract_id="acct.position", contract_version="v1",
            entity_type="position",
            fields=(
                ContractFieldSnapshot("market_value", "decimal", required=True),
            ),
        )
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [
                {"entity_ref": {"id": "1"}, "fields": {"market_value": "100"}},
            ]},
            contract_snapshot=contract,
        ))
        assert result.outcome.is_valid is True

    def test_type_mismatch_emits_finding(self):
        contract = ContractSnapshot(
            contract_id="acct.position", contract_version="v1",
            entity_type="position",
            fields=(
                ContractFieldSnapshot("count", "integer", required=False),
            ),
        )
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [
                {"entity_ref": {"id": "1"}, "fields": {"count": "not_an_int"}},
            ]},
            contract_snapshot=contract,
        ))
        codes = {f.finding_code for f in result.findings if not f.passed}
        assert finding_codes.CONTRACT_TYPE_MISMATCH in codes

    def test_nullable_false_rejects_none(self):
        contract = ContractSnapshot(
            contract_id="acct.position", contract_version="v1",
            entity_type="position",
            fields=(
                ContractFieldSnapshot(
                    "market_value", "decimal",
                    required=True, nullable=False,
                ),
            ),
        )
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [
                # Field is present but explicitly null.
                {"entity_ref": {"id": "1"}, "fields": {"market_value": None}},
            ]},
            contract_snapshot=contract,
        ))
        # nullable=False means the required check fails on None.
        assert result.summary.failed_count >= 1

    def test_nullable_true_allows_none(self):
        contract = ContractSnapshot(
            contract_id="acct.position", contract_version="v1",
            entity_type="position",
            fields=(
                ContractFieldSnapshot(
                    "market_value", "decimal",
                    required=False, nullable=True,
                ),
            ),
        )
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [
                {"entity_ref": {"id": "1"}, "fields": {"market_value": None}},
            ]},
            contract_snapshot=contract,
        ))
        # The contract type check sees None and accepts it (nullable).
        assert result.outcome.is_valid is True

    def test_required_entity_ref_key_missing_emits_finding(self):
        contract = ContractSnapshot(
            contract_id="acct.position", contract_version="v1",
            entity_type="position",
            required_entity_ref_keys=("account_id",),
        )
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [
                {"entity_ref": {"id": "1"}, "fields": {}},  # no account_id
            ]},
            contract_snapshot=contract,
        ))
        rule_ids_with_failures = {
            f.rule_id for f in result.findings if not f.passed
        }
        assert any(
            "entity_ref.account_id" in rid
            for rid in rule_ids_with_failures
        )

    def test_synthetic_rule_ids_appear_in_summary(self):
        contract = ContractSnapshot(
            contract_id="acct.position", contract_version="v1",
            entity_type="position",
            fields=(
                ContractFieldSnapshot("market_value", "decimal", required=True),
            ),
        )
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [
                {"entity_ref": {"id": "1"}, "fields": {}},
            ]},
            contract_snapshot=contract,
        ))
        # Synthetic rule_id is stable and discoverable.
        rule_ids_in_results = {r.rule_id for r in result.rule_results}
        assert any(
            rid.startswith("_contract.acct.position.market_value")
            for rid in rule_ids_in_results
        )

    def test_contract_findings_count_in_aggregations(self):
        contract = ContractSnapshot(
            contract_id="c", contract_version="v1",
            entity_type="record",
            fields=(
                ContractFieldSnapshot("x", "integer", required=True),
                ContractFieldSnapshot("y", "string", required=True),
            ),
        )
        result = self._engine().validate(ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": [
                {"entity_ref": {"id": "1"}, "fields": {}},
            ]},
            contract_snapshot=contract,
        ))
        assert result.summary.by_finding_code.get(
            finding_codes.CONTRACT_FIELD_MISSING, 0
        ) >= 2
