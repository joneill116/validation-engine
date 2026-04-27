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

from ..models.applicability import RuleApplicability
from ..models.dependency import RuleDependency
from ..models.enums import Category, Scope, Severity


@dataclass(frozen=True)
class ReferenceDataRef:
    """
    Pointer to reference data the engine should make available.

    ``inline`` may be a mapping, list, or scalar — the engine treats it
    opaquely. ``path`` loads the value from a YAML/JSON file via the
    compiler's ``config_dir``.
    """
    name: str
    path: str | None = None
    inline: Any = None


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
        applies_when: Optional ``RuleApplicability`` that gates whether
            the rule runs for a given target.
        depends_on: Tuple of ``RuleDependency`` describing prerequisite
            rules and the mode of dependency.
        group_id: Optional rule-group membership (set by the loader when
            a rule lives inside a ``rule_groups`` block).
    """

    rule_id: str
    rule_type: str
    scope: Scope | None = None
    # ``None`` here means "the rule didn't say". The factory resolves
    # missing values to sensible defaults (BLOCKING / STRUCTURAL) when
    # building the runtime ``Rule`` instance. The distinction matters at
    # the loader: rule_groups can apply ``default_severity`` only when
    # the rule itself didn't specify one (so explicit overrides win).
    severity: Severity | None = None
    category: Category | None = None
    field_path: str = "*"
    applies_to: tuple[str, ...] = ("*",)
    params: Mapping[str, Any] = field(default_factory=dict)
    message: str | None = None
    rule_version: str = "1.0"
    enabled: bool = True
    applies_when: RuleApplicability = field(default_factory=RuleApplicability)
    depends_on: tuple[RuleDependency, ...] = field(default_factory=tuple)
    group_id: str | None = None

    def __post_init__(self) -> None:
        normalized = _normalize_applies_to(self.applies_to)
        if normalized is not self.applies_to:
            object.__setattr__(self, "applies_to", normalized)
        if not isinstance(self.depends_on, tuple):
            object.__setattr__(self, "depends_on", tuple(self.depends_on))


@dataclass(frozen=True)
class StrategyConfig:
    """Configuration for the strategy bound to the ruleset."""
    strategy_type: str = "severity_gate"
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleGroupConfig:
    """
    A named group of rules with shared default severity/category.

    Group-level defaults apply to a rule only when the rule itself does
    not override them. Membership in a disabled group disables every rule
    in the group.
    """
    group_id: str
    description: str = ""
    enabled: bool = True
    default_severity: Severity | None = None
    default_category: Category | None = None
    rules: tuple[RuleConfig, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RulesetConfig:
    """
    Top-level ruleset configuration.

    Fields:
        ruleset_id: Identifier referenced by ValidationRequest.ruleset_id.
        ruleset_version: Version pin (audit trail).
        entity_type: Entity type the ruleset targets.
        description: Human-readable summary.
        rules: List of rule configs (groups are flattened into ``rules``
            after the loader expands them, with ``group_id`` stamped).
        rule_groups: List of rule-group configs the loader will expand.
            The compiler reads ``rules`` only; groups are an authoring-
            time convenience that gets flattened.
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
    rule_groups: tuple[RuleGroupConfig, ...] = field(default_factory=tuple)
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
