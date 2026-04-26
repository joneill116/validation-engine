"""Tests for RulesetCompiler — config -> executable rules."""
import pytest

from validation_engine import (
    ReferenceDataRef,
    RuleConfig,
    RulesetCompiler,
    RulesetConfig,
    Severity,
    SeverityGateStrategy,
    StrategyConfig,
)
from validation_engine.rules.standard import EnumRule, RequiredRule


def _config(rules):
    return RulesetConfig(
        ruleset_id="rs1",
        ruleset_version="v1",
        entity_type="record",
        rules=tuple(rules),
        strategy=StrategyConfig(
            strategy_type="severity_gate",
            params={"publish_target": "p", "exception_target": "e"},
        ),
    )


class TestCompiler:
    def test_compiles_each_rule(self):
        cfg = _config([
            RuleConfig(
                rule_id="r1", rule_type="required",
                field_path="acct",
                severity=Severity.BLOCKING,
            ),
            RuleConfig(
                rule_id="r2", rule_type="enum",
                field_path="cat", params={"values": ["X", "Y"]},
            ),
        ])
        compiled = RulesetCompiler().compile(cfg)
        assert len(compiled.rules) == 2
        assert isinstance(compiled.rules[0], RequiredRule)
        assert isinstance(compiled.rules[1], EnumRule)
        assert compiled.rules[0].rule_id == "r1"
        assert compiled.rules[1].rule_id == "r2"

    def test_unknown_rule_type_raises(self):
        cfg = _config([RuleConfig(rule_id="r1", rule_type="not_a_real_type")])
        with pytest.raises(KeyError):
            RulesetCompiler().compile(cfg)

    def test_strategy_built(self):
        compiled = RulesetCompiler().compile(_config([]))
        assert isinstance(compiled.strategy, SeverityGateStrategy)
        assert compiled.strategy.publish_target == "p"
        assert compiled.strategy.exception_target == "e"

    def test_duplicate_rule_ids_rejected(self):
        cfg = _config([
            RuleConfig(rule_id="r.same", rule_type="required", field_path="a"),
            RuleConfig(rule_id="r.same", rule_type="required", field_path="b"),
        ])
        with pytest.raises(ValueError, match="Duplicate rule_id"):
            RulesetCompiler().compile(cfg)

    def test_disabled_rule_with_duplicate_id_ignored(self):
        # The disabled rule shouldn't trigger the duplicate check.
        cfg = _config([
            RuleConfig(rule_id="r.same", rule_type="required", field_path="a"),
            RuleConfig(
                rule_id="r.same", rule_type="required", field_path="b",
                enabled=False,
            ),
        ])
        compiled = RulesetCompiler().compile(cfg)  # no exception
        assert len(compiled.rules) == 1

    def test_disabled_rules_are_skipped(self):
        cfg = _config([
            RuleConfig(
                rule_id="r1", rule_type="required",
                field_path="acct",
                enabled=False,
            ),
            RuleConfig(
                rule_id="r2", rule_type="required",
                field_path="acct",
            ),
        ])
        compiled = RulesetCompiler().compile(cfg)
        assert [r.rule_id for r in compiled.rules] == ["r2"]

    def test_reference_data_inline_loaded(self):
        cfg = RulesetConfig(
            ruleset_id="rs1",
            ruleset_version="v1",
            entity_type="record",
            rules=(),
            strategy=StrategyConfig(strategy_type="severity_gate"),
            reference_data=(
                ReferenceDataRef(
                    name="window",
                    inline={"start": "2026-01-01", "end": "2026-12-31"},
                ),
            ),
        )
        compiled = RulesetCompiler().compile(cfg)
        assert "window" in compiled.reference_data
        assert compiled.reference_data["window"]["start"] == "2026-01-01"

    def test_reference_data_missing_path_raises(self, tmp_path):
        cfg = RulesetConfig(
            ruleset_id="rs1", ruleset_version="v1", entity_type="record",
            rules=(),
            strategy=StrategyConfig(strategy_type="severity_gate"),
            reference_data=(
                ReferenceDataRef(name="missing", path=str(tmp_path / "nope.json")),
            ),
        )
        with pytest.raises(FileNotFoundError):
            RulesetCompiler().compile(cfg)

    def test_unknown_strategy_type_raises(self):
        cfg = RulesetConfig(
            ruleset_id="rs1", ruleset_version="v1", entity_type="record",
            rules=(),
            strategy=StrategyConfig(strategy_type="not_a_strategy"),
        )
        with pytest.raises(KeyError):
            RulesetCompiler().compile(cfg)

    def test_custom_strategy_builder_used(self):
        from validation_engine.strategies.severity_gate import SeverityGateStrategy

        def custom_builder(strategy_config):
            return SeverityGateStrategy(publish_target="custom")

        compiled = RulesetCompiler(strategy_builder=custom_builder).compile(_config([]))
        assert compiled.strategy.publish_target == "custom"


class TestDirectRuleConfigDefense:
    """``RuleConfig(applies_to="x")`` (string) must not iterate to chars."""

    def test_string_applies_to_normalized(self):
        cfg = RuleConfig(
            rule_id="r", rule_type="required", field_path="x",
            applies_to="record",  # type: ignore[arg-type]  intentional misuse
        )
        assert cfg.applies_to == ("record",)

    def test_compiled_rule_inherits_normalized_applies_to(self):
        cfg = RuleConfig(
            rule_id="r", rule_type="required", field_path="x",
            applies_to="record",  # type: ignore[arg-type]
        )
        compiled_rule = RulesetCompiler().compile(_config([cfg])).rules[0]
        assert compiled_rule.applies_to == frozenset({"record"})


class TestConfiguredRuleDefense:
    """Direct ``ConfiguredRule(applies_to="x")`` must not iterate chars."""

    def test_string_applies_to_normalized(self):
        from validation_engine.rules.standard import RequiredRule
        rule = RequiredRule(rule_id="r", field_path="x", applies_to="record")
        assert rule.applies_to == frozenset({"record"})
