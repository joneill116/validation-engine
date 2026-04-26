"""Tests for ConfigLoader (YAML and JSON)."""
import json
import textwrap

import pytest

from validation_engine import ConfigLoader, RuleConfig, RulesetConfig
from validation_engine.config.loader import ConfigLoadError


YAML_TEXT = textwrap.dedent("""
    ruleset_id: test_ruleset
    ruleset_version: v1
    entity_type: record
    description: hello
    strategy:
      strategy_type: severity_gate
      params:
        publish_target: t.publish
    reference_data:
      - name: window
        inline:
          start: "2026-01-01"
          end: "2026-12-31"
    rules:
      - rule_id: r.required_a
        rule_type: required
        severity: blocking
        category: completeness
        field_path: field_a
        params:
          field: field_a
      - rule_id: r.enum
        rule_type: enum
        severity: warning
        field_path: field_b
        params:
          values: [X, Y]
""").strip()


JSON_TEXT = json.dumps({
    "ruleset_id": "json_ruleset",
    "ruleset_version": "v1",
    "entity_type": "record",
    "rules": [
        {
            "rule_id": "r.required_a",
            "rule_type": "required",
            "field_path": "field_a",
            "params": {"field": "field_a"},
        }
    ],
})


def _yaml_available():
    try:
        import yaml  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _yaml_available(), reason="PyYAML not installed")
class TestYamlLoading:
    def test_load_from_string(self):
        cfg = ConfigLoader().loads(YAML_TEXT, fmt="yaml")
        assert isinstance(cfg, RulesetConfig)
        assert cfg.ruleset_id == "test_ruleset"
        assert cfg.entity_type == "record"
        assert cfg.description == "hello"
        assert len(cfg.rules) == 2
        assert cfg.strategy.strategy_type == "severity_gate"
        assert cfg.strategy.params["publish_target"] == "t.publish"

    def test_rule_fields_parsed(self):
        cfg = ConfigLoader().loads(YAML_TEXT, fmt="yaml")
        r0: RuleConfig = cfg.rules[0]
        assert r0.rule_id == "r.required_a"
        assert r0.rule_type == "required"
        assert r0.severity.value == "blocking"
        assert r0.field_path == "field_a"
        assert r0.params == {"field": "field_a"}

    def test_load_file(self, tmp_path):
        p = tmp_path / "rs.yaml"
        p.write_text(YAML_TEXT, encoding="utf-8")
        cfg = ConfigLoader().load(p)
        assert cfg.ruleset_id == "test_ruleset"

    def test_reference_data_inline(self):
        cfg = ConfigLoader().loads(YAML_TEXT, fmt="yaml")
        assert len(cfg.reference_data) == 1
        ref = cfg.reference_data[0]
        assert ref.name == "window"
        assert ref.inline == {"start": "2026-01-01", "end": "2026-12-31"}


class TestJsonLoading:
    def test_load_json_string(self):
        cfg = ConfigLoader().loads(JSON_TEXT, fmt="json")
        assert cfg.ruleset_id == "json_ruleset"
        assert len(cfg.rules) == 1


class TestErrors:
    def test_missing_required_keys(self):
        with pytest.raises(ConfigLoadError):
            ConfigLoader().from_dict({"rules": []})

    def test_rule_missing_keys(self):
        with pytest.raises(ConfigLoadError):
            ConfigLoader().from_dict({
                "ruleset_id": "x", "entity_type": "y",
                "rules": [{"rule_id": "r"}],  # no rule_type
            })

    def test_load_file_missing(self, tmp_path):
        with pytest.raises(ConfigLoadError):
            ConfigLoader().load(tmp_path / "nope.yaml")

    def test_invalid_severity_value_wrapped(self):
        with pytest.raises(ConfigLoadError) as exc:
            ConfigLoader().from_dict({
                "ruleset_id": "rs1", "entity_type": "record",
                "rules": [{
                    "rule_id": "r1", "rule_type": "required",
                    "severity": "critical",  # not a valid Severity value
                }],
            })
        # Surface a clear error message including the invalid value
        assert "critical" in str(exc.value)
        assert "Severity" in str(exc.value)

    def test_unsupported_extension_raises(self, tmp_path):
        p = tmp_path / "rs.toml"
        p.write_text("ruleset_id: x", encoding="utf-8")
        with pytest.raises(ConfigLoadError):
            ConfigLoader().load(p)


class TestAppliesToParsing:
    """A bare string in YAML must NOT be split into characters."""

    def test_string_applies_to_treated_as_single_value(self):
        cfg = ConfigLoader().from_dict({
            "ruleset_id": "rs1", "entity_type": "record",
            "rules": [{
                "rule_id": "r1", "rule_type": "required",
                "field_path": "x",
                "applies_to": "record",  # not a list
            }],
        })
        assert cfg.rules[0].applies_to == ("record",)

    def test_list_applies_to_preserved(self):
        cfg = ConfigLoader().from_dict({
            "ruleset_id": "rs1", "entity_type": "record",
            "rules": [{
                "rule_id": "r1", "rule_type": "required",
                "field_path": "x",
                "applies_to": ["a", "b"],
            }],
        })
        assert cfg.rules[0].applies_to == ("a", "b")

    def test_invalid_applies_to_type_raises(self):
        with pytest.raises(ConfigLoadError):
            ConfigLoader().from_dict({
                "ruleset_id": "rs1", "entity_type": "record",
                "rules": [{
                    "rule_id": "r1", "rule_type": "required",
                    "field_path": "x",
                    "applies_to": 123,  # nonsense
                }],
            })

    def test_default_applies_to_is_wildcard(self):
        cfg = ConfigLoader().from_dict({
            "ruleset_id": "rs1", "entity_type": "record",
            "rules": [{
                "rule_id": "r1", "rule_type": "required", "field_path": "x",
            }],
        })
        assert cfg.rules[0].applies_to == ("*",)


class TestStringTypeEnforcement:
    """Numeric/None values where strings are expected must be rejected or coerced."""

    def test_non_string_ruleset_id_raises(self):
        with pytest.raises(ConfigLoadError, match="ruleset_id"):
            ConfigLoader().from_dict({
                "ruleset_id": 123, "entity_type": "x", "rules": [],
            })

    def test_non_string_field_path_raises(self):
        with pytest.raises(ConfigLoadError):
            ConfigLoader().from_dict({
                "ruleset_id": "rs1", "entity_type": "record",
                "rules": [{
                    "rule_id": "r1", "rule_type": "required", "field_path": 123,
                }],
            })

    def test_numeric_rule_version_coerced_to_string(self):
        # YAML scalars like ``rule_version: 1.0`` should be accepted gracefully.
        cfg = ConfigLoader().from_dict({
            "ruleset_id": "rs1", "entity_type": "record",
            "rules": [{
                "rule_id": "r1", "rule_type": "required", "field_path": "x",
                "rule_version": 1.0,
            }],
        })
        assert cfg.rules[0].rule_version == "1.0"
