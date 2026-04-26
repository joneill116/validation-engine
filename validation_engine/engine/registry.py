"""
Registries for dynamic rule and strategy selection.

Enables runtime selection of rules and strategies based on
entity type, ruleset identifier, and strategy identifier.
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..rules.base import Rule
    from ..strategies.base import PublishStrategy

logger = logging.getLogger(__name__)


class RuleRegistry:
    """
    Maps (entity_type, ruleset_id) → list[Rule].
    
    Supports multiple entity types and rulesets in a single engine instance.
    Rules can be registered incrementally or in batches.
    
    Example:
        registry = RuleRegistry()
        registry.register("record", "standard:v1", [Rule1(), Rule2()])
        registry.register("event", "standard:v1", [Rule3(), Rule4()])
        
        # Later retrieve
        rules = registry.get("record", "standard:v1")
    """

    def __init__(self) -> None:
        self._rulesets: dict[tuple[str, str], list["Rule"]] = {}

    def register(self, entity_type: str, ruleset_id: str, rules: list["Rule"]) -> None:
        """
        Register rules for a specific entity type and ruleset.
        
        Can be called multiple times with the same key to extend the ruleset.
        
        Args:
            entity_type: Classification of entities (e.g., "record", "event")
            ruleset_id: Unique identifier for this ruleset (e.g., "standard:v1")
            rules: List of rule instances to register
        """
        if not entity_type or not entity_type.strip():
            raise ValueError("entity_type cannot be empty")
        
        if not ruleset_id or not ruleset_id.strip():
            raise ValueError("ruleset_id cannot be empty")
        
        if not rules:
            logger.warning(
                f"Registering empty rule list for entity_type={entity_type!r}, "
                f"ruleset_id={ruleset_id!r}"
            )
        
        key = (entity_type.strip(), ruleset_id.strip())
        self._rulesets.setdefault(key, []).extend(rules)
        
        logger.info(
            f"Registered {len(rules)} rules for entity_type={entity_type!r}, "
            f"ruleset_id={ruleset_id!r} (total: {len(self._rulesets[key])})"
        )

    def get(self, entity_type: str, ruleset_id: str) -> list["Rule"]:
        """
        Retrieve rules for a specific entity type and ruleset.
        
        Args:
            entity_type: Classification of entities
            ruleset_id: Unique identifier for the ruleset
            
        Returns:
            List of registered rules
            
        Raises:
            KeyError: If no rules are registered for the given combination
        """
        key = (entity_type, ruleset_id)
        rules = self._rulesets.get(key, [])
        
        if not rules:
            available = ", ".join(f"({et!r}, {rid!r})" for et, rid in self._rulesets.keys())
            raise KeyError(
                f"No rules registered for entity_type={entity_type!r}, ruleset_id={ruleset_id!r}. "
                f"Available: {available if available else 'none'}"
            )
        
        return rules
    
    def list_keys(self) -> list[tuple[str, str]]:
        """
        List all registered (entity_type, ruleset_id) combinations.
        
        Returns:
            List of tuples (entity_type, ruleset_id)
        """
        return list(self._rulesets.keys())
    
    def clear(self) -> None:
        """Remove all registered rules."""
        self._rulesets.clear()
        logger.info("Rule registry cleared")


class StrategyRegistry:
    """
    Maps strategy_id → PublishStrategy.
    
    Enables dynamic strategy selection at validation time.
    
    Example:
        registry = StrategyRegistry()
        registry.register(SeverityGateStrategy(...))
        registry.register(FieldPartitionStrategy(...))
        
        # Later retrieve
        strategy = registry.get("severity_gate")
    """

    def __init__(self) -> None:
        self._strategies: dict[str, "PublishStrategy"] = {}

    def register(self, strategy: "PublishStrategy") -> None:
        """
        Register a strategy by its strategy_id.
        
        Overwrites any existing strategy with the same ID.
        
        Args:
            strategy: Strategy instance with a strategy_id attribute
        """
        if not hasattr(strategy, "strategy_id"):
            raise ValueError("Strategy must have a 'strategy_id' attribute")
        
        strategy_id = strategy.strategy_id
        
        if not strategy_id or not isinstance(strategy_id, str):
            raise ValueError(f"strategy_id must be a non-empty string, got {strategy_id!r}")
        
        if strategy_id in self._strategies:
            logger.warning(f"Overwriting existing strategy: {strategy_id!r}")
        
        self._strategies[strategy_id] = strategy
        logger.info(f"Registered strategy: {strategy_id!r}")

    def get(self, strategy_id: str) -> "PublishStrategy":
        """
        Retrieve a strategy by its identifier.
        
        Args:
            strategy_id: Unique strategy identifier
            
        Returns:
            Strategy instance
            
        Raises:
            KeyError: If strategy not found
        """
        strategy = self._strategies.get(strategy_id)
        
        if strategy is None:
            available = ", ".join(f"{sid!r}" for sid in self._strategies.keys())
            raise KeyError(
                f"No strategy registered for strategy_id={strategy_id!r}. "
                f"Available: {available if available else 'none'}"
            )
        
        return strategy
    
    def list_ids(self) -> list[str]:
        """
        List all registered strategy IDs.
        
        Returns:
            List of strategy identifiers
        """
        return list(self._strategies.keys())
    
    def clear(self) -> None:
        """Remove all registered strategies."""
        self._strategies.clear()
        logger.info("Strategy registry cleared")
