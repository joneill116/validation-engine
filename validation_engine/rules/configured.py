"""
ConfiguredRule — base class for rules built from typed configuration.

Each standard rule type (``required``, ``enum``, ``range``, ...) inherits
from ``ConfiguredRule`` and accepts its tunable behaviour via
``params``. ``ConfiguredRule`` itself stays abstract — subclasses must
implement ``evaluate``.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..models.enums import Category, Scope, Severity
from .base import Rule


class ConfiguredRule(Rule):
    """Abstract base for rules instantiated from a ``RuleConfig``."""

    rule_type: str = "configured"

    def __init__(
        self,
        rule_id: str,
        *,
        params: Mapping[str, Any] | None = None,
        scope: Scope = Scope.FIELD,
        severity: Severity = Severity.BLOCKING,
        category: Category = Category.STRUCTURAL,
        field_path: str = "*",
        applies_to: Iterable[str] | None = None,
        rule_version: str = "1.0",
        message: str | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.rule_version = rule_version
        self.scope = scope
        self.severity = severity
        self.category = category
        self.field_path = field_path
        self.applies_to = _to_frozenset(applies_to)
        self.params: dict[str, Any] = dict(params or {})
        self._message_override = message

    def _message(self, default: str) -> str:
        return self._message_override or default


def _to_frozenset(applies_to: Iterable[str] | None) -> frozenset[str]:
    """Normalize ``applies_to`` to a frozenset, treating a bare string as one entry."""
    if applies_to is None:
        return frozenset({"*"})
    if isinstance(applies_to, str):
        return frozenset({applies_to})
    return frozenset(applies_to) or frozenset({"*"})
