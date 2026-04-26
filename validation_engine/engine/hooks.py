"""
Lifecycle hooks for observability and extensibility.

Allows external systems to observe and react to validation events.
"""
import time
from types import MappingProxyType
from typing import Any, Callable
from dataclasses import dataclass
from ..contracts.findings import Finding
from ..contracts.results import CollectionResult, EntityResult
from ..contracts.actions import StrategyDecision


@dataclass(frozen=True)
class ValidationEvent:
    """Base class for all validation events."""
    timestamp: float
    entity_type: str
    ruleset_id: str


@dataclass(frozen=True)
class ValidationStartEvent(ValidationEvent):
    """Fired when validation begins."""
    collection_id: str
    entity_count: int
    rule_count: int


@dataclass(frozen=True)
class ValidationCompleteEvent(ValidationEvent):
    """Fired when validation completes successfully."""
    collection_id: str
    duration_ms: float
    result: CollectionResult
    decision: StrategyDecision


@dataclass(frozen=True)
class ValidationErrorEvent(ValidationEvent):
    """Fired when validation fails with an error."""
    collection_id: str
    error: Exception
    duration_ms: float


@dataclass(frozen=True)
class RuleExecutionEvent(ValidationEvent):
    """Fired for each rule execution."""
    rule_id: str
    scope: str
    duration_ms: float
    finding: Finding


@dataclass(frozen=True)
class EntityProcessedEvent(ValidationEvent):
    """Fired when an entity completes validation."""
    entity_ref: MappingProxyType
    result: EntityResult
    duration_ms: float


class ValidationHooks:
    """
    Hook registry for validation lifecycle events.
    
    Supports multiple listeners per event type for metrics, logging, alerting, etc.
    All hooks are called synchronously during validation.
    
    Example:
        hooks = ValidationHooks()
        hooks.on_validation_start(lambda e: print(f"Started {e.collection_id}"))
        hooks.on_validation_complete(lambda e: metrics.record(e.duration_ms))
    """
    
    def __init__(self):
        self._start_listeners: list[Callable[[ValidationStartEvent], None]] = []
        self._complete_listeners: list[Callable[[ValidationCompleteEvent], None]] = []
        self._error_listeners: list[Callable[[ValidationErrorEvent], None]] = []
        self._rule_listeners: list[Callable[[RuleExecutionEvent], None]] = []
        self._entity_listeners: list[Callable[[EntityProcessedEvent], None]] = []
    
    def on_validation_start(self, callback: Callable[[ValidationStartEvent], None]) -> None:
        """Register listener for validation start events."""
        self._start_listeners.append(callback)
    
    def on_validation_complete(self, callback: Callable[[ValidationCompleteEvent], None]) -> None:
        """Register listener for validation complete events."""
        self._complete_listeners.append(callback)
    
    def on_validation_error(self, callback: Callable[[ValidationErrorEvent], None]) -> None:
        """Register listener for validation error events."""
        self._error_listeners.append(callback)
    
    def on_rule_execution(self, callback: Callable[[RuleExecutionEvent], None]) -> None:
        """Register listener for individual rule executions."""
        self._rule_listeners.append(callback)
    
    def on_entity_processed(self, callback: Callable[[EntityProcessedEvent], None]) -> None:
        """Register listener for entity processing completion."""
        self._entity_listeners.append(callback)
    
    def emit_start(self, event: ValidationStartEvent) -> None:
        """Emit validation start event to all registered listeners."""
        for listener in self._start_listeners:
            try:
                listener(event)
            except Exception:
                # Hook failures should not break validation
                pass
    
    def emit_complete(self, event: ValidationCompleteEvent) -> None:
        """Emit validation complete event to all registered listeners."""
        for listener in self._complete_listeners:
            try:
                listener(event)
            except Exception:
                pass
    
    def emit_error(self, event: ValidationErrorEvent) -> None:
        """Emit validation error event to all registered listeners."""
        for listener in self._error_listeners:
            try:
                listener(event)
            except Exception:
                pass
    
    def emit_rule_execution(self, event: RuleExecutionEvent) -> None:
        """Emit rule execution event to all registered listeners."""
        for listener in self._rule_listeners:
            try:
                listener(event)
            except Exception:
                pass
    
    def emit_entity_processed(self, event: EntityProcessedEvent) -> None:
        """Emit entity processed event to all registered listeners."""
        for listener in self._entity_listeners:
            try:
                listener(event)
            except Exception:
                pass
    
    def clear_all(self) -> None:
        """Remove all registered listeners."""
        self._start_listeners.clear()
        self._complete_listeners.clear()
        self._error_listeners.clear()
        self._rule_listeners.clear()
        self._entity_listeners.clear()
