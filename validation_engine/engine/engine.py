import hashlib
import json
import logging
import time
from types import MappingProxyType
from typing import Any, Optional
from .context import EvaluationContext
from .evaluator import Evaluator
from .registry import RuleRegistry, StrategyRegistry
from .validation import validate_payload, validate_entity_type, validate_ruleset_id, validate_metadata, PayloadValidationError
from .hooks import ValidationHooks, ValidationStartEvent, ValidationCompleteEvent, ValidationErrorEvent
from .cache import RuleCache
from ..contracts.actions import StrategyDecision
from ..rules.base import Rule
from ..strategies.base import PublishStrategy

logger = logging.getLogger(__name__)


class ValidationEngine:
    """
    Main entry point for the validation library.
    
    Domain-agnostic validation engine supporting configurable rules,
    strategies, hooks, and caching for high-performance data validation.

    Basic Usage:
        from validation_engine import ValidationEngine, SeverityGateStrategy
        from my_rules import RequiredFieldRule, FormatRule

        engine = ValidationEngine(
            rules=[RequiredFieldRule(), FormatRule()],
            strategy=SeverityGateStrategy(
                publish_target="topic.valid",
                exception_target="topic.invalid",
            ),
        )

        decision = engine.validate(
            payload={"entities": [{"entity_ref": {...}, "fields": {...}}, ...]},
            entity_type="record",
            ruleset_id="record:standard:v1",
        )

        for action in decision.actions:
            print(action.action_type, action.target, action.entity_ref)

    Registry-Based Configuration:
        engine = ValidationEngine.from_registries(
            rule_registry=rule_reg,
            strategy_registry=strategy_reg,
        )

        decision = engine.validate(
            payload=payload,
            entity_type="record",
            ruleset_id="record:standard:v1",
            strategy_id="field_partition",
        )
    
    Advanced Features:
        # Enable caching for performance
        engine = ValidationEngine(
            rules=rules,
            strategy=strategy,
            enable_cache=True,
            cache_size=50000,
        )
        
        # Add observability hooks
        engine.hooks.on_validation_complete(
            lambda e: print(f"Validated in {e.duration_ms}ms")
        )
        
        # Get cache statistics
        stats = engine.get_cache_stats()
    """

    def __init__(
        self,
        rules: list[Rule],
        strategy: PublishStrategy,
        rules_config_version: str = "latest",
        reference_data: dict[str, Any] | None = None,
        enable_cache: bool = False,
        cache_size: int = 10000,
        hooks: Optional[ValidationHooks] = None,
    ) -> None:
        """
        Initialize validation engine with direct configuration.
        
        Args:
            rules: List of rule instances to execute
            strategy: Publishing strategy for routing results
            rules_config_version: Version identifier for rule configuration
            reference_data: Static lookup data available to all rules
            enable_cache: Enable result caching for performance (default: False)
            cache_size: Maximum cached entries if caching enabled (default: 10000)
            hooks: Custom hook registry for lifecycle events
        """
        self._rules = rules
        self._strategy = strategy
        self._rules_config_version = rules_config_version
        
        # Validate reference_data is JSON-serializable for cache consistency
        if reference_data:
            try:
                json.dumps(reference_data, ensure_ascii=False)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"reference_data must be JSON-serializable for cache consistency. "
                    f"Contains non-serializable objects: {e}"
                )
        
        self._reference_data = reference_data or {}
        self._rule_registry: RuleRegistry | None = None
        self._strategy_registry: StrategyRegistry | None = None
        
        # Validate cache_size if caching enabled
        if enable_cache:
            if cache_size <= 0:
                raise ValueError(f"cache_size must be positive, got {cache_size}")
            if cache_size > 10_000_000:
                logger.warning(
                    f"Large cache_size ({cache_size:,}) may impact memory usage. "
                    f"Consider using a smaller value for production."
                )
        
        self._cache: Optional[RuleCache] = RuleCache(cache_size) if enable_cache else None
        self.hooks: ValidationHooks = hooks or ValidationHooks()
        
        logger.info(
            f"Initialized ValidationEngine: {len(rules)} rules, "
            f"strategy={getattr(strategy, 'strategy_id', 'unknown')}, "
            f"cache={'enabled' if enable_cache else 'disabled'}"
        )

    @classmethod
    def from_registries(
        cls,
        rule_registry: RuleRegistry,
        strategy_registry: StrategyRegistry,
        rules_config_version: str = "latest",
        reference_data: dict[str, Any] | None = None,
        enable_cache: bool = False,
        cache_size: int = 10000,
        hooks: Optional[ValidationHooks] = None,
    ) -> "ValidationEngine":
        """
        Create engine with registry-based rule and strategy selection.
        
        Allows dynamic selection of rules and strategies at validation time
        based on entity_type, ruleset_id, and strategy_id parameters.
        
        Args:
            rule_registry: Registry mapping (entity_type, ruleset_id) to rules
            strategy_registry: Registry mapping strategy_id to strategies
            rules_config_version: Version identifier for rule configuration
            reference_data: Static lookup data available to all rules
            enable_cache: Enable result caching for performance (default: False)
            cache_size: Maximum cached entries if caching enabled (default: 10000)
            hooks: Custom hook registry for lifecycle events
            
        Returns:
            ValidationEngine instance configured for registry-based operation
        """
        instance = cls.__new__(cls)
        instance._rules = []
        instance._strategy = None  # type: ignore[assignment]
        instance._rules_config_version = rules_config_version
        
        # Validate reference_data is JSON-serializable for cache consistency
        if reference_data:
            try:
                json.dumps(reference_data, ensure_ascii=False)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"reference_data must be JSON-serializable for cache consistency. "
                    f"Contains non-serializable objects: {e}"
                )
        
        instance._reference_data = reference_data or {}
        instance._rule_registry = rule_registry
        instance._strategy_registry = strategy_registry
        
        # Validate cache_size if caching enabled
        if enable_cache:
            if cache_size <= 0:
                raise ValueError(f"cache_size must be positive, got {cache_size}")
            if cache_size > 10_000_000:
                logger.warning(
                    f"Large cache_size ({cache_size:,}) may impact memory usage. "
                    f"Consider using a smaller value for production."
                )
        
        instance._cache = RuleCache(cache_size) if enable_cache else None
        instance.hooks = hooks or ValidationHooks()
        
        logger.info(
            "Initialized ValidationEngine from registries: "
            f"cache={'enabled' if enable_cache else 'disabled'}"
        )
        
        return instance

    def validate(
        self,
        payload: dict[str, Any],
        entity_type: str,
        ruleset_id: str,
        strategy_id: str | None = None,
        collection_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StrategyDecision:
        """
        Validate a payload and return a StrategyDecision.
        
        Validates input structure, evaluates all applicable rules,
        and applies the configured strategy to determine routing actions.

        Args:
            payload: {"entities": [{"entity_ref": {...}, "fields": {...}}, ...]}
            entity_type: Classification of entities being validated (e.g., "record", "event")
            ruleset_id: Identifier for the ruleset to apply (e.g., "standard:v1")
            strategy_id: Strategy identifier (required when using from_registries())
            collection_id: Optional deterministic ID; auto-derived from payload if omitted
            metadata: Optional key-value pairs passed to EvaluationContext
            
        Returns:
            StrategyDecision containing routing actions and summary
            
        Raises:
            PayloadValidationError: If payload structure is invalid
            ValueError: If entity_type, ruleset_id, or other params are invalid
            KeyError: If requested rules or strategy not found in registries
        """
        start_time = time.perf_counter()
        
        # Validate all inputs upfront
        validated_payload = validate_payload(payload)
        entity_type = validate_entity_type(entity_type)
        ruleset_id = validate_ruleset_id(ruleset_id)
        metadata = validate_metadata(metadata)
        
        # Resolve configuration
        rules = self._resolve_rules(entity_type, ruleset_id)
        strategy = self._resolve_strategy(strategy_id)
        
        # Create evaluation context with immutable mappings
        ctx = EvaluationContext(
            entity_type=entity_type,
            ruleset_id=ruleset_id,
            rules_config_version=self._rules_config_version,
            reference_data=MappingProxyType(self._reference_data),
            metadata=MappingProxyType(metadata),
        )
        
        # Generate or use provided collection ID
        cid = collection_id or self._derive_collection_id(validated_payload, entity_type, ruleset_id)
        
        # Emit start event
        self.hooks.emit_start(ValidationStartEvent(
            timestamp=start_time,
            entity_type=entity_type,
            ruleset_id=ruleset_id,
            collection_id=cid,
            entity_count=len(validated_payload["entities"]),
            rule_count=len(rules),
        ))
        
        logger.info(
            f"Starting validation: collection_id={cid}, entity_type={entity_type}, "
            f"ruleset_id={ruleset_id}, entities={len(validated_payload['entities'])}, rules={len(rules)}"
        )
        
        try:
            # Execute validation
            evaluator = Evaluator(rules, cache=self._cache, hooks=self.hooks)
            result = evaluator.evaluate(validated_payload, ctx, cid)
            
            # Apply strategy
            decision = strategy.decide(result)
            
            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Emit complete event
            self.hooks.emit_complete(ValidationCompleteEvent(
                timestamp=time.perf_counter(),
                entity_type=entity_type,
                ruleset_id=ruleset_id,
                collection_id=cid,
                duration_ms=duration_ms,
                result=result,
                decision=decision,
            ))
            
            logger.info(
                f"Validation complete: collection_id={cid}, duration={duration_ms:.2f}ms, "
                f"actions={len(decision.actions)}"
            )
            
            return decision
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Emit error event
            self.hooks.emit_error(ValidationErrorEvent(
                timestamp=time.perf_counter(),
                entity_type=entity_type,
                ruleset_id=ruleset_id,
                collection_id=cid,
                error=e,
                duration_ms=duration_ms,
            ))
            
            logger.error(
                f"Validation failed: collection_id={cid}, error={type(e).__name__}: {e}",
                exc_info=True
            )
            
            raise

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    
    def get_cache_stats(self) -> dict[str, int | float] | None:
        """
        Get cache performance statistics.
        
        Returns:
            Dictionary with hits, misses, size, max_size (int), and hit_rate_percent (float),
            or None if caching is disabled
        """
        return self._cache.stats() if self._cache else None
    
    def clear_cache(self) -> None:
        """Clear all cached rule results."""
        if self._cache:
            self._cache.clear()
            logger.info("Rule cache cleared")
    
    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_rules(self, entity_type: str, ruleset_id: str) -> list[Rule]:
        """Resolve rules from registry or direct configuration."""
        if self._rule_registry is not None:
            try:
                return self._rule_registry.get(entity_type, ruleset_id)
            except KeyError as e:
                logger.error(
                    f"Rules not found: entity_type={entity_type!r}, ruleset_id={ruleset_id!r}"
                )
                raise
        return self._rules

    def _resolve_strategy(self, strategy_id: str | None) -> PublishStrategy:
        """Resolve strategy from registry or direct configuration."""
        if self._strategy_registry is not None and strategy_id is not None:
            try:
                return self._strategy_registry.get(strategy_id)
            except KeyError:
                logger.error(f"Strategy not found: strategy_id={strategy_id!r}")
                raise
        
        if self._strategy is not None:
            return self._strategy
        
        raise ValueError(
            "No strategy available. Either pass strategy= at construction "
            "or use from_registries() and provide strategy_id= to validate()."
        )

    @staticmethod
    def _derive_collection_id(
        payload: dict[str, Any], entity_type: str, ruleset_id: str
    ) -> str:
        # Extract entity identifiers for deterministic collection ID
        refs = []
        for e in payload.get("entities", []):
            entity_ref = e.get("entity_ref", {})
            # Try common ID fields in order: id, subject_ref_id, entity_id
            ref_id = entity_ref.get("id") or entity_ref.get("subject_ref_id") or entity_ref.get("entity_id") or ""
            refs.append(ref_id)
        digest_input = json.dumps(
            {"entity_type": entity_type, "ruleset_id": ruleset_id, "refs": sorted(refs)},
            sort_keys=True,
        )
        return hashlib.sha256(digest_input.encode()).hexdigest()[:16]
