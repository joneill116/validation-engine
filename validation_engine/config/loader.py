"""
ConfigLoader — parse YAML/JSON ruleset definitions into RulesetConfig.

YAML support requires PyYAML. JSON works out of the box.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from ..models.applicability import (
    ApplicabilityPredicate,
    PredicateOperator,
    RuleApplicability,
)
from ..models.dependency import DependencyMode, RuleDependency
from ..models.enums import Category, Scope, Severity
from .schema import (
    ReferenceDataRef,
    RuleConfig,
    RuleGroupConfig,
    RulesetConfig,
    StrategyConfig,
)


class ConfigLoadError(ValueError):
    """Raised when a ruleset config file cannot be parsed."""


class ConfigLoader:
    """Load ruleset configuration from YAML/JSON files or strings."""

    def load(self, path: str | os.PathLike) -> RulesetConfig:
        p = Path(path)
        if not p.exists():
            raise ConfigLoadError(f"Config file not found: {p}")
        text = p.read_text(encoding="utf-8")
        suffix = p.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            return self.from_dict(self._parse_yaml(text, source=str(p)))
        if suffix == ".json":
            return self.from_dict(self._parse_json(text, source=str(p)))
        raise ConfigLoadError(
            f"Unsupported config file extension {suffix!r}. Use .yaml/.yml/.json."
        )

    def loads(self, text: str, fmt: str = "yaml") -> RulesetConfig:
        if fmt.lower() in {"yaml", "yml"}:
            return self.from_dict(self._parse_yaml(text, source="<string>"))
        if fmt.lower() == "json":
            return self.from_dict(self._parse_json(text, source="<string>"))
        raise ConfigLoadError(f"Unsupported format: {fmt}")

    # ------------------------------------------------------------------
    # parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_yaml(text: str, source: str) -> Mapping[str, Any]:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ConfigLoadError(
                "PyYAML is required to load YAML ruleset configs. "
                "Install with: pip install pyyaml"
            ) from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:  # type: ignore
            raise ConfigLoadError(f"YAML parse error in {source}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigLoadError(f"{source}: top-level YAML must be a mapping")
        return data

    @staticmethod
    def _parse_json(text: str, source: str) -> Mapping[str, Any]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigLoadError(f"JSON parse error in {source}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigLoadError(f"{source}: top-level JSON must be an object")
        return data

    # ------------------------------------------------------------------
    # data -> RulesetConfig
    # ------------------------------------------------------------------

    def from_dict(self, data: Mapping[str, Any]) -> RulesetConfig:
        try:
            ruleset_id = _require_str(data.get("ruleset_id"), "ruleset_id")
            entity_type = _require_str(data.get("entity_type"), "entity_type")
            ruleset_version = _coerce_version(data.get("ruleset_version"), "v1")
            description = _coerce_str(data.get("description"), "")
        except ValueError as exc:
            raise ConfigLoadError(
                f"Ruleset config: {exc}"
            ) from exc
        loose_rules = tuple(self._rule_from_dict(r) for r in data.get("rules") or [])
        groups = tuple(self._rule_group_from_dict(g) for g in data.get("rule_groups") or [])
        # Flatten group rules into the same ``rules`` tuple the compiler
        # consumes, applying group-level severity/category defaults and
        # cascading the group's enabled flag. Group-only rules carry the
        # ``group_id`` so summaries can aggregate by group.
        flattened_groups: list[RuleConfig] = []
        for group in groups:
            for rule in group.rules:
                flattened_groups.append(_apply_group_defaults(rule, group))
        rules = loose_rules + tuple(flattened_groups)
        strategy = self._strategy_from_dict(data.get("strategy"))
        ref_data = tuple(self._refdata_from_dict(r) for r in data.get("reference_data") or [])
        return RulesetConfig(
            ruleset_id=ruleset_id,
            ruleset_version=ruleset_version,
            entity_type=entity_type,
            description=description,
            rules=rules,
            rule_groups=groups,
            strategy=strategy,
            reference_data=ref_data,
            metadata=dict(data.get("metadata") or {}),
        )

    @staticmethod
    def _rule_from_dict(data: Mapping[str, Any]) -> RuleConfig:
        if not isinstance(data, dict):
            raise ConfigLoadError(
                f"Rule entry must be a mapping, got {type(data).__name__}"
            )
        rule_id_raw = data.get("rule_id") or data.get("id")
        rule_type_raw = data.get("rule_type") or data.get("type")
        if not rule_id_raw or not rule_type_raw:
            raise ConfigLoadError(
                f"Rule entry missing 'rule_id' or 'rule_type': {data!r}"
            )
        try:
            rule_id = _require_str(rule_id_raw, "rule_id")
            rule_type = _require_str(rule_type_raw, "rule_type")
            field_path = _coerce_str(data.get("field_path"), "*")
            scope = _parse_enum(Scope, data.get("scope"), allow_none=True)
            # Pass through ``None`` when the YAML didn't set the key so the
            # schema can tell defaulted vs explicit. The factory resolves
            # ``None`` to BLOCKING/STRUCTURAL when constructing the Rule.
            severity = _parse_enum(Severity, data.get("severity"), allow_none=True)
            category = _parse_enum(Category, data.get("category"), allow_none=True)
            applies_to = _parse_applies_to(data.get("applies_to"))
            applies_when = _parse_applies_when(data.get("applies_when"))
            depends_on = _parse_depends_on(data.get("depends_on"))
        except ValueError as exc:
            raise ConfigLoadError(
                f"Rule {rule_id_raw!r}: {exc}"
            ) from exc
        return RuleConfig(
            rule_id=rule_id,
            rule_type=rule_type,
            scope=scope,
            severity=severity,
            category=category,
            field_path=field_path,
            applies_to=applies_to,
            params=dict(data.get("params") or {}),
            message=data.get("message"),
            rule_version=_coerce_version(data.get("rule_version"), "1.0"),
            enabled=bool(data.get("enabled", True)),
            applies_when=applies_when,
            depends_on=depends_on,
            group_id=data.get("group_id"),
        )

    def _rule_group_from_dict(self, data: Mapping[str, Any]) -> RuleGroupConfig:
        if not isinstance(data, dict):
            raise ConfigLoadError(
                f"rule_group entry must be a mapping, got {type(data).__name__}"
            )
        group_id_raw = data.get("group_id") or data.get("id")
        if not group_id_raw:
            raise ConfigLoadError(f"rule_group missing 'group_id': {data!r}")
        try:
            group_id = _require_str(group_id_raw, "group_id")
            default_severity = _parse_enum(
                Severity, data.get("default_severity") or data.get("severity"),
                allow_none=True,
            )
            default_category = _parse_enum(
                Category, data.get("default_category") or data.get("category"),
                allow_none=True,
            )
        except ValueError as exc:
            raise ConfigLoadError(f"rule_group {group_id_raw!r}: {exc}") from exc
        rules = tuple(self._rule_from_dict(r) for r in data.get("rules") or [])
        return RuleGroupConfig(
            group_id=group_id,
            description=_coerce_str(data.get("description"), ""),
            enabled=bool(data.get("enabled", True)),
            default_severity=default_severity,
            default_category=default_category,
            rules=rules,
            metadata=dict(data.get("metadata") or {}),
        )

    @staticmethod
    def _strategy_from_dict(data: Mapping[str, Any] | None) -> StrategyConfig:
        if not data:
            return StrategyConfig()
        return StrategyConfig(
            strategy_type=data.get("strategy_type") or data.get("type", "severity_gate"),
            params=dict(data.get("params") or {}),
        )

    @staticmethod
    def _refdata_from_dict(data: Mapping[str, Any]) -> ReferenceDataRef:
        name = data.get("name")
        if not name:
            raise ConfigLoadError(
                f"reference_data entry missing 'name': {data!r}"
            )
        return ReferenceDataRef(
            name=name,
            path=data.get("path"),
            inline=data.get("inline"),
        )


def load_ruleset(path: str | os.PathLike) -> RulesetConfig:
    """Convenience wrapper used in quick-start examples."""
    return ConfigLoader().load(path)


def _parse_enum(enum_cls, value, *, allow_none: bool = False):
    """Convert a string to an enum value, raising a clear ValueError on miss."""
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"missing {enum_cls.__name__} value")
    try:
        return enum_cls(value)
    except ValueError:
        valid = ", ".join(repr(m.value) for m in enum_cls)
        raise ValueError(
            f"{value!r} is not a valid {enum_cls.__name__}; valid: {valid}"
        ) from None


def _require_str(value: Any, name: str) -> str:
    """Validate ``value`` is a non-empty string, returning it."""
    if not isinstance(value, str):
        raise ValueError(
            f"{name} must be a string, got {type(value).__name__}"
        )
    if not value:
        raise ValueError(f"{name} cannot be empty")
    return value


def _coerce_str(value: Any, default: str) -> str:
    """Return ``value`` (string), the default for None, or raise."""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    raise ValueError(f"expected string, got {type(value).__name__}")


def _coerce_version(value: Any, default: str) -> str:
    """
    Like ``_coerce_str`` but accepts YAML scalar numbers (``rule_version: 1.0``).
    """
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    raise ValueError(f"expected string, got {type(value).__name__}")


def _parse_applies_when(value: Any) -> RuleApplicability:
    """Parse the YAML/dict ``applies_when`` block into a ``RuleApplicability``."""
    if value is None:
        return RuleApplicability()
    if not isinstance(value, Mapping):
        raise ValueError(
            f"applies_when must be a mapping, got {type(value).__name__}"
        )
    raw_predicates = value.get("predicates") or value.get("when") or []
    if not isinstance(raw_predicates, list):
        raise ValueError("applies_when.predicates must be a list")
    predicates: list[ApplicabilityPredicate] = []
    for entry in raw_predicates:
        if not isinstance(entry, Mapping):
            raise ValueError(
                f"applies_when predicate must be a mapping, got {type(entry).__name__}"
            )
        field_path = entry.get("field_path") or entry.get("field")
        if not field_path:
            raise ValueError("applies_when predicate missing 'field_path'")
        op_raw = entry.get("operator", "equals")
        try:
            op = PredicateOperator(op_raw)
        except ValueError:
            valid = ", ".join(repr(o.value) for o in PredicateOperator)
            raise ValueError(f"unknown applies_when operator {op_raw!r}; valid: {valid}") from None
        predicates.append(ApplicabilityPredicate(
            field_path=field_path, operator=op, value=entry.get("value"),
        ))
    match = value.get("match", "all")
    if match not in ("all", "any"):
        raise ValueError(f"applies_when.match must be 'all' or 'any', got {match!r}")
    return RuleApplicability(predicates=tuple(predicates), match=match)


def _parse_depends_on(value: Any) -> tuple[RuleDependency, ...]:
    """Parse the YAML/dict ``depends_on`` block into ``RuleDependency`` tuples."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(
            f"depends_on must be a list, got {type(value).__name__}"
        )
    deps: list[RuleDependency] = []
    for entry in value:
        if isinstance(entry, str):
            deps.append(RuleDependency(rule_id=entry))
            continue
        if not isinstance(entry, Mapping):
            raise ValueError(
                f"depends_on entry must be a string or mapping, got {type(entry).__name__}"
            )
        rule_id = entry.get("rule_id")
        if not rule_id:
            raise ValueError("depends_on entry missing 'rule_id'")
        mode_raw = entry.get("mode", "requires_pass")
        try:
            mode = DependencyMode(mode_raw)
        except ValueError:
            valid = ", ".join(repr(m.value) for m in DependencyMode)
            raise ValueError(f"unknown depends_on mode {mode_raw!r}; valid: {valid}") from None
        deps.append(RuleDependency(rule_id=rule_id, mode=mode))
    return tuple(deps)


def _apply_group_defaults(rule: RuleConfig, group: RuleGroupConfig) -> RuleConfig:
    """
    Stamp the group_id onto a rule and apply group-level defaults.

    A rule that explicitly set ``severity``/``category`` keeps them —
    group defaults only fill in unset values (``None`` from the loader).
    The group's ``enabled`` flag cascades multiplicatively (group
    disabled => rule disabled).
    """
    from dataclasses import replace
    new_severity = rule.severity
    new_category = rule.category
    # Only fill in when the rule didn't say. ``None`` is the loader's
    # signal that the YAML omitted the key.
    if rule.severity is None and group.default_severity is not None:
        new_severity = group.default_severity
    if rule.category is None and group.default_category is not None:
        new_category = group.default_category
    return replace(
        rule,
        severity=new_severity,
        category=new_category,
        enabled=rule.enabled and group.enabled,
        group_id=group.group_id,
    )


def _parse_applies_to(value: Any) -> tuple[str, ...]:
    """
    Normalize ``applies_to`` to a tuple of entity-type strings.

    YAML lets users write a single value without brackets; we accept that
    rather than splitting the string into characters.
    """
    if value is None:
        return ("*",)
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        if not all(isinstance(v, str) for v in value):
            raise ValueError(
                f"applies_to must contain strings, got {value!r}"
            )
        return tuple(value) or ("*",)
    raise ValueError(
        f"applies_to must be a string or list of strings, got {type(value).__name__}"
    )
