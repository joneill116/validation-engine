"""
RuleFactory — builds executable Rule instances from RuleConfig.

Standard rule types are registered by default. Custom rule types can
be registered at runtime; once registered, they become referenceable
from YAML/JSON configs by name.
"""
from __future__ import annotations

from typing import Callable, Type

from ..models.enums import Category, Severity
from ..rules.base import Rule
from ..rules.standard import STANDARD_RULES
from .schema import RuleConfig


RuleBuilder = Callable[[RuleConfig], Rule]


class RuleFactory:
    """
    Factory for instantiating rules from typed configuration.

    Usage::

        factory = RuleFactory()
        factory.register("my_custom_type", MyCustomRule)  # class taking RuleConfig
        rule = factory.build(rule_config)
    """

    def __init__(self) -> None:
        self._builders: dict[str, RuleBuilder] = {}
        # Register all standard rule types
        for rule_type, cls in STANDARD_RULES.items():
            self.register_class(rule_type, cls)

    # ------------------------------------------------------------------
    # registration
    # ------------------------------------------------------------------

    def register(self, rule_type: str, builder: RuleBuilder) -> None:
        """Register a custom builder function for a rule_type."""
        if not rule_type or not isinstance(rule_type, str):
            raise ValueError(f"rule_type must be a non-empty string, got {rule_type!r}")
        self._builders[rule_type] = builder

    def register_class(self, rule_type: str, cls: Type) -> None:
        """Register a rule class. Class must accept (rule_id, **kwargs)."""

        def _builder(cfg: RuleConfig, _cls: Type = cls) -> Rule:
            kwargs = self._kwargs_from_config(cfg)
            return _cls(rule_id=cfg.rule_id, **kwargs)

        self.register(rule_type, _builder)

    def types(self) -> list[str]:
        return sorted(self._builders.keys())

    # ------------------------------------------------------------------
    # building
    # ------------------------------------------------------------------

    def build(self, cfg: RuleConfig) -> Rule:
        if cfg.rule_type not in self._builders:
            raise KeyError(
                f"Unknown rule_type {cfg.rule_type!r}. "
                f"Registered types: {self.types()}"
            )
        builder = self._builders[cfg.rule_type]
        return builder(cfg)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _kwargs_from_config(cfg: RuleConfig) -> dict:
        # Resolve the loader's "not specified" sentinels (None) to the
        # documented defaults so the runtime Rule always carries a real
        # Severity/Category. ``None`` only flows through the schema layer
        # so group defaults can tell explicit-vs-defaulted apart.
        kwargs: dict = {
            "params": dict(cfg.params),
            "severity": cfg.severity if cfg.severity is not None else Severity.BLOCKING,
            "category": cfg.category if cfg.category is not None else Category.STRUCTURAL,
            "field_path": cfg.field_path,
            "applies_to": set(cfg.applies_to),
            "rule_version": cfg.rule_version,
            "message": cfg.message,
            "applies_when": cfg.applies_when,
            "depends_on": cfg.depends_on,
            "group_id": cfg.group_id,
        }
        if cfg.scope is not None:
            kwargs["scope"] = cfg.scope
        return kwargs
