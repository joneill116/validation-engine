from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from .enums import ActionType


@dataclass(frozen=True)
class Action:
    """Immutable action with routing decision.
    
    Uses MappingProxyType for entity_ref and payload to enforce true immutability.
    """
    action_type: ActionType
    entity_ref: MappingProxyType
    payload: MappingProxyType
    target: str
    rationale: str


@dataclass(frozen=True)
class StrategyDecision:
    """Immutable strategy decision containing routing actions.
    
    Frozen to prevent mutation after strategies create decisions.
    """
    strategy_id: str
    strategy_version: str
    actions: tuple[Action, ...] = field(default_factory=tuple)
    summary: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def by_action_type(self, action_type: ActionType) -> tuple[Action, ...]:
        """Filter actions by type."""
        return tuple(a for a in self.actions if a.action_type == action_type)
