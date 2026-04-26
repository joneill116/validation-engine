"""
Evaluation context for rule execution.

Provides immutable shared state that flows through the entire validation pipeline.
"""
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class EvaluationContext:
    """
    Immutable context carrying per-evaluation metadata available to every rule.
    
    Provides rules with access to:
    - Entity classification (entity_type)
    - Ruleset identifier (ruleset_id)
    - Configuration version for audit trails
    - Reference data for lookups (country codes, allowed values, etc.)
    - Additional metadata for custom rule logic
    
    Immutability ensures rules cannot modify shared state, preventing
    side effects and enabling safe caching and parallelization.
    
    Example:
        ctx = EvaluationContext(
            entity_type="record",
            ruleset_id="standard:v1",
            rules_config_version="2024.4",
            reference_data={
                "valid_countries": ["US", "GB", "DE"],
                "allowed_statuses": ["active", "inactive"],
            },
            metadata={
                "processing_date": "2024-01-15",
                "source_system": "upstream_api",
            },
        )
        
        # Rules can access context
        def evaluate(self, target, ctx):
            valid_values = ctx.reference_data.get("valid_countries", [])
            return make_finding(
                self,
                passed=target in valid_values,
                message=f"{target} not in {valid_values}"
            )
    """
    
    entity_type: str
    """Classification of entities being validated (e.g., 'record', 'event', 'transaction')."""
    
    ruleset_id: str
    """Unique identifier for the active ruleset (e.g., 'standard:v1', 'strict:v2')."""
    
    rules_config_version: str
    """Version identifier for the rule configuration (for audit trails and rollback)."""
    
    reference_data: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    """
    Static lookup tables for rule evaluation.
    
    Keeps hardcoded values out of rules and makes them configurable.
    Examples: country codes, currency lists, allowed enumerations.
    Injected at engine construction, not fetched by rules.
    Immutable via MappingProxyType to enforce true context immutability.
    """
    
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    """
    Additional key-value pairs for custom rule logic.
    
    Can include processing timestamps, source system identifiers,
    tenant IDs, or any other contextual information needed by rules.
    Immutable via MappingProxyType - metadata cannot affect validation outcomes
    and is excluded from cache key calculation.
    """

