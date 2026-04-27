"""Tests for ValidationRequest model and engine acceptance of it."""
import pytest

from validation_engine import (
    PayloadValidationError,
    SeverityGateStrategy,
    ValidationEngine,
    ValidationRequest,
    ValidationResult,
)
from validation_engine.testing import field_rule


def _payload():
    return {"entities": [{"entity_ref": {"id": "e1"}, "fields": {"x": 1}}]}


class TestValidationRequest:
    def test_required_fields(self):
        with pytest.raises(ValueError):
            ValidationRequest(payload={}, ruleset_id="r1")  # missing entity_type
        with pytest.raises(ValueError):
            ValidationRequest(payload={}, entity_type="t")  # missing ruleset_id

    def test_defaults_are_filled(self):
        req = ValidationRequest(
            entity_type="record",
            ruleset_id="r1",
            payload=_payload(),
        )
        assert req.request_id.startswith("req_")
        assert req.tenant_id == "default"
        assert req.ruleset_version == "latest"
        assert req.metadata == {}

    def test_metadata_is_immutable(self):
        req = ValidationRequest(
            entity_type="record",
            ruleset_id="r1",
            payload=_payload(),
            metadata={"tenant": "abc"},
        )
        with pytest.raises(TypeError):
            req.metadata["tenant"] = "xyz"  # type: ignore[index]

    def test_payload_is_deep_copied_at_construction(self):
        # Mutating the original input dict must not change request.payload.
        # Audit replay depends on the request being a stable snapshot.
        original = {"entities": [{"entity_ref": {"id": "e1"}, "fields": {"x": 1}}]}
        req = ValidationRequest(
            entity_type="record", ruleset_id="r1", payload=original,
        )
        original["entities"].append({"entity_ref": {"id": "e2"}, "fields": {"x": 2}})
        original["entities"][0]["fields"]["x"] = 999
        assert len(req.payload["entities"]) == 1
        assert req.payload["entities"][0]["fields"]["x"] == 1


class TestEngineAcceptsRequest:
    def test_validate_request_returns_validation_result(self):
        engine = ValidationEngine(
            rules=[field_rule(rule_id="r.ok", passes=True)],
            strategy=SeverityGateStrategy(),
        )
        req = ValidationRequest(
            entity_type="record", ruleset_id="rs1", payload=_payload(),
        )
        result = engine.validate(req)
        assert isinstance(result, ValidationResult)
        assert result.request_id == req.request_id

    def test_validate_kwargs_compat(self):
        engine = ValidationEngine(
            rules=[field_rule(rule_id="r.ok", passes=True)],
            strategy=SeverityGateStrategy(),
        )
        result = engine.validate(
            payload=_payload(), entity_type="record", ruleset_id="rs1",
        )
        assert isinstance(result, ValidationResult)

    def test_validate_rejects_request_plus_kwargs(self):
        engine = ValidationEngine(
            rules=[field_rule(passes=True)], strategy=SeverityGateStrategy(),
        )
        req = ValidationRequest(
            entity_type="record", ruleset_id="rs1", payload=_payload(),
        )
        # Combining a request with request-shaped kwargs is ambiguous.
        with pytest.raises(ValueError, match="both a ValidationRequest"):
            engine.validate(req, payload={"entities": []})
        with pytest.raises(ValueError, match="both a ValidationRequest"):
            engine.validate(req, ruleset_version="v2")


class TestPayloadValidation:
    def test_missing_entities_key_raises(self):
        engine = ValidationEngine(
            rules=[field_rule(passes=True)], strategy=SeverityGateStrategy(),
        )
        req = ValidationRequest(
            entity_type="record", ruleset_id="rs1", payload={"not_entities": []},
        )
        with pytest.raises(PayloadValidationError):
            engine.validate(req)

    def test_entities_not_a_list_raises(self):
        engine = ValidationEngine(
            rules=[field_rule(passes=True)], strategy=SeverityGateStrategy(),
        )
        req = ValidationRequest(
            entity_type="record", ruleset_id="rs1", payload={"entities": "nope"},
        )
        with pytest.raises(PayloadValidationError):
            engine.validate(req)

    def test_entity_must_be_a_dict(self):
        engine = ValidationEngine(
            rules=[field_rule(passes=True)], strategy=SeverityGateStrategy(),
        )
        req = ValidationRequest(
            entity_type="record", ruleset_id="rs1",
            payload={"entities": ["not a dict"]},
        )
        with pytest.raises(PayloadValidationError):
            engine.validate(req)
