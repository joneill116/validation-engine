"""
Builders for tests.

These are intentionally tiny helpers — not fluent DSLs. They exist so
test code can construct the most common shapes without naming every
default. The validation engine has a lot of fields by design; these
builders absorb the boilerplate so tests stay focused on the assertion.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..config.schema import RuleConfig, RulesetConfig, StrategyConfig
from ..models.enums import Category, Scope, Severity
from ..models.finding import ValidationFinding
from ..models.request import ValidationRequest


def request_builder(
    *,
    entity_type: str = "record",
    ruleset_id: str = "rs1",
    ruleset_version: str = "v1",
    entities: Iterable[Mapping[str, Any]] = (),
    metadata: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> ValidationRequest:
    """Build a minimal ``ValidationRequest`` from a list of entities."""
    return ValidationRequest(
        entity_type=entity_type,
        ruleset_id=ruleset_id,
        ruleset_version=ruleset_version,
        payload={"entities": [dict(e) for e in entities]},
        metadata=metadata or {},
        **kwargs,
    )


def entity_builder(
    *,
    entity_id: str | None = None,
    entity_ref: Mapping[str, Any] | None = None,
    fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical entity envelope."""
    ref = dict(entity_ref or {})
    if entity_id is not None and "id" not in ref:
        ref["id"] = entity_id
    return {"entity_ref": ref, "fields": dict(fields or {})}


def ruleset_builder(
    *,
    ruleset_id: str = "rs1",
    ruleset_version: str = "v1",
    entity_type: str = "record",
    rules: Iterable[RuleConfig] = (),
    strategy: StrategyConfig | None = None,
) -> RulesetConfig:
    """Build a ``RulesetConfig`` with sensible defaults."""
    return RulesetConfig(
        ruleset_id=ruleset_id,
        ruleset_version=ruleset_version,
        entity_type=entity_type,
        rules=tuple(rules),
        strategy=strategy or StrategyConfig(strategy_type="severity_gate"),
    )


def finding_builder(
    *,
    rule_id: str = "test.rule",
    passed: bool = False,
    severity: Severity = Severity.BLOCKING,
    category: Category = Category.STRUCTURAL,
    message: str = "test finding",
    finding_code: str = "",
    field_path: str | None = None,
    expected: Any = None,
    actual: Any = None,
    entity_ref: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> ValidationFinding:
    """Build a ``ValidationFinding`` for tests."""
    return ValidationFinding(
        rule_id=rule_id,
        severity=severity,
        category=category,
        passed=passed,
        message=message,
        finding_code=finding_code,
        field_path=field_path,
        expected=expected,
        actual=actual,
        entity_ref=entity_ref or {},
        **kwargs,
    )
