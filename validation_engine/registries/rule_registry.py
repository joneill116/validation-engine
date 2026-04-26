"""
RuleRegistry — maps (entity_type, ruleset_id) -> rules.

Lets the engine resolve which rules to run for a given ValidationRequest.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..rules.base import Rule


class RuleRegistry:
    def __init__(self) -> None:
        self._rulesets: dict[tuple[str, str], list["Rule"]] = {}

    def register(
        self, entity_type: str, ruleset_id: str, rules: list["Rule"]
    ) -> None:
        if not entity_type or not entity_type.strip():
            raise ValueError("entity_type cannot be empty")
        if not ruleset_id or not ruleset_id.strip():
            raise ValueError("ruleset_id cannot be empty")
        key = (entity_type.strip(), ruleset_id.strip())
        self._rulesets.setdefault(key, []).extend(rules)

    def get(self, entity_type: str, ruleset_id: str) -> list["Rule"]:
        key = (entity_type.strip(), ruleset_id.strip())
        rules = self._rulesets.get(key)
        if not rules:
            available = ", ".join(f"({et!r}, {rid!r})" for et, rid in self._rulesets)
            raise KeyError(
                f"No rules registered for entity_type={entity_type!r}, "
                f"ruleset_id={ruleset_id!r}. Available: {available or 'none'}"
            )
        return list(rules)
