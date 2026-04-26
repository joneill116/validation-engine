"""
ConfigLoader — parse YAML/JSON ruleset definitions into RulesetConfig.

YAML support requires PyYAML. JSON works out of the box.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from ..models.enums import Category, Scope, Severity
from .schema import (
    ReferenceDataRef,
    RuleConfig,
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
        rules = tuple(self._rule_from_dict(r) for r in data.get("rules") or [])
        strategy = self._strategy_from_dict(data.get("strategy"))
        ref_data = tuple(self._refdata_from_dict(r) for r in data.get("reference_data") or [])
        return RulesetConfig(
            ruleset_id=ruleset_id,
            ruleset_version=ruleset_version,
            entity_type=entity_type,
            description=description,
            rules=rules,
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
            severity = _parse_enum(Severity, data.get("severity", "blocking"))
            category = _parse_enum(Category, data.get("category", "structural"))
            applies_to = _parse_applies_to(data.get("applies_to"))
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
