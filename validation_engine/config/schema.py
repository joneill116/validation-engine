"""
Typed configuration schema.

A ``RulesetConfig`` is the in-memory representation of a YAML/JSON
ruleset definition. The schema is intentionally conservative: it does
not allow arbitrary expressions / lambdas. Anything more complex than
a structured rule must be implemented as a Python rule class and
referenced by ``rule_type``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..models.enums import Category, Scope, Severity


@dataclass(frozen=True)
class ReferenceDataRef:
    """Pointer to reference data the engine should make available."""
    name: str
    path: str | None = None
    inline: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class RuleConfig:
    """
    Typed configuration for one rule.

    Fields:
        rule_id: Stable identifier.
        rule_type: Standard rule type (``required``, ``enum``, ...) or
            the name of a registered custom rule.
        scope: Scope for the rule. Defaults vary by rule type.
        severity: Severity assigned to non-passing findings.
        category: Functional category.
        field_path: Field this rule targets (FIELD scope).
        applies_to: Entity types this rule covers. A bare string is
            normalized to a single-element tuple so direct construction
            is safe against ``RuleConfig(applies_to="x")`` typos.
        params: Type-specific parameters (passed through to the rule).
        message: Optional override for the failure message.
        rule_version: Version pin.
        enabled: When False, the compiler skips this rule.
    """

    rule_id: str
    rule_type: str
    scope: Scope | None = None
    severity: Severity = Severity.BLOCKING
    category: Category = Category.STRUCTURAL
    field_path: str = "*"
    applies_to: tuple[str, ...] = ("*",)
    params: Mapping[str, Any] = field(default_factory=dict)
    message: str | None = None
    rule_version: str = "1.0"
    enabled: bool = True

    def __post_init__(self) -> None:
        normalized = _normalize_applies_to(self.applies_to)
        if normalized is not self.applies_to:
            object.__setattr__(self, "applies_to", normalized)


@dataclass(frozen=True)
class StrategyConfig:
    """Configuration for the strategy bound to the ruleset."""
    strategy_type: str = "severity_gate"
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RulesetConfig:
    """
    Top-level ruleset configuration.

    Fields:
        ruleset_id: Identifier referenced by ValidationRequest.ruleset_id.
        ruleset_version: Version pin (audit trail).
        entity_type: Entity type the ruleset targets.
        description: Human-readable summary.
        rules: List of rule configs.
        strategy: Strategy binding (defaults to severity_gate).
        reference_data: Pointers / inline reference data the engine
            should expose to rules via EvaluationContext.
        metadata: Free-form key-value pairs (owner, tags, etc).
    """

    ruleset_id: str
    ruleset_version: str
    entity_type: str
    description: str = ""
    rules: tuple[RuleConfig, ...] = field(default_factory=tuple)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    reference_data: tuple[ReferenceDataRef, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _normalize_applies_to(value: Any) -> tuple[str, ...]:
    """Normalize an ``applies_to`` value to a tuple of strings.

    Auto-wraps a bare string (avoids ``tuple("foo")`` char-iteration).
    """
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple) and all(isinstance(v, str) for v in value):
        return value
    return tuple(value)
