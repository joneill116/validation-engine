"""
Domain-Agnostic Validation Engine.

High-performance, configuration-driven validation library with
pluggable rules, strategies, caching, and observability hooks.

Basic Usage:
    from validation_engine import ValidationEngine, SeverityGateStrategy
    from my_rules import MyRule
    
    engine = ValidationEngine(
        rules=[MyRule()],
        strategy=SeverityGateStrategy(
            publish_target="valid_queue",
            exception_target="invalid_queue",
        ),
    )
    
    decision = engine.validate(
        payload={"entities": [...]},
        entity_type="record",
        ruleset_id="standard:v1",
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
        lambda e: print(f"Completed in {e.duration_ms}ms")
    )
    
    # Get cache statistics
    stats = engine.get_cache_stats()
"""

# ── core engine ──────────────────────────────────────────────────────────────
from .engine.engine import ValidationEngine
from .engine.registry import RuleRegistry, StrategyRegistry
from .engine.context import EvaluationContext
from .engine.hooks import (
    ValidationHooks,
    ValidationEvent,
    ValidationStartEvent,
    ValidationCompleteEvent,
    ValidationErrorEvent,
    RuleExecutionEvent,
    EntityProcessedEvent,
)
from .engine.cache import RuleCache
from .engine.validation import PayloadValidationError

# ── contracts ─────────────────────────────────────────────────────────────────
from .contracts.enums import Severity, Scope, Category, Disposition, ActionType
from .contracts.findings import Finding
from .contracts.results import FieldResult, EntityResult, CollectionResult
from .contracts.actions import Action, StrategyDecision

# ── rule authoring ────────────────────────────────────────────────────────────
from .rules.base import Rule, make_finding

# ── built-in strategies ───────────────────────────────────────────────────────
from .strategies.base import PublishStrategy
from .strategies.severity_gate import SeverityGateStrategy
from .strategies.field_partition import FieldPartitionStrategy
from .strategies.strict import StrictStrategy

__version__ = "1.0.0"

__all__ = [
    # engine
    "ValidationEngine",
    "RuleRegistry",
    "StrategyRegistry",
    "EvaluationContext",
    # hooks and observability
    "ValidationHooks",
    "ValidationEvent",
    "ValidationStartEvent",
    "ValidationCompleteEvent",
    "ValidationErrorEvent",
    "RuleExecutionEvent",
    "EntityProcessedEvent",
    # cache
    "RuleCache",
    # validation
    "PayloadValidationError",
    # contracts
    "Severity", "Scope", "Category", "Disposition", "ActionType",
    "Finding",
    "FieldResult", "EntityResult", "CollectionResult",
    "Action", "StrategyDecision",
    # rules
    "Rule", "make_finding",
    # strategies
    "PublishStrategy",
    "SeverityGateStrategy",
    "FieldPartitionStrategy",
    "StrictStrategy",
    # metadata
    "__version__",
]
