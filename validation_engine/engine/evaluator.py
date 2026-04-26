import time
import logging
import copy
from types import MappingProxyType
from typing import Any, TYPE_CHECKING, Optional
from ..contracts.enums import Scope
from ..contracts.findings import Finding
from ..contracts.results import FieldResult, EntityResult, CollectionResult
from .context import EvaluationContext
from .safe_execution import safe_evaluate_rule
from .cache import RuleCache, make_cache_key, hash_context
from .hooks import ValidationHooks, RuleExecutionEvent, EntityProcessedEvent

if TYPE_CHECKING:
    from ..rules.base import Rule

logger = logging.getLogger(__name__)


class Evaluator:
    """
    Runs a ruleset against a payload and returns a CollectionResult.

    Executes rules in hierarchical order with optional caching for performance:
      1. FIELD rules   — run per-field against each entity
      2. ENTITY rules  — run against the whole entity record
      3. COLLECTION rules — run against the full batch

    Field rules receive the field value as target.
    Entity rules receive the full entity dict as target.
    Collection rules receive the list of entity dicts as target.
    
    Supports result caching for deterministic rules to avoid redundant computation.
    Emits lifecycle events through hooks for observability.
    """

    def __init__(
        self,
        rules: list["Rule"],
        cache: Optional[RuleCache] = None,
        hooks: Optional[ValidationHooks] = None,
    ) -> None:
        """
        Initialize evaluator with rules and optional extensions.
        
        Args:
            rules: List of rules to evaluate
            cache: Optional cache for rule results
            hooks: Optional hook registry for lifecycle events
        """
        self._field_rules = [r for r in rules if r.scope == Scope.FIELD]
        self._entity_rules = [r for r in rules if r.scope == Scope.ENTITY]
        self._collection_rules = [r for r in rules if r.scope == Scope.COLLECTION]
        self._cache = cache
        self._hooks = hooks or ValidationHooks()

    def evaluate(
        self,
        payload: dict[str, Any],
        ctx: EvaluationContext,
        collection_id: str,
    ) -> CollectionResult:
        raw_entities: list[dict[str, Any]] = payload.get("entities", [])
        entity_results: list[EntityResult] = []

        for raw in raw_entities:
            entity_results.append(self._evaluate_entity(raw, ctx))

        collection_findings = self._evaluate_collection(raw_entities, ctx)

        return CollectionResult(
            collection_id=collection_id,
            entity_type=ctx.entity_type,
            ruleset_id=ctx.ruleset_id,
            entities=tuple(entity_results),
            collection_findings=tuple(collection_findings),
        )

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    def _evaluate_entity(
        self, raw: dict[str, Any], ctx: EvaluationContext
    ) -> EntityResult:
        """Evaluate all field and entity rules for a single entity."""
        start_time = time.perf_counter()
        
        # Deep copy entity_ref to prevent mutations through MappingProxyType view
        entity_ref: dict[str, Any] = raw.get("entity_ref", {})
        entity_ref_copy = copy.deepcopy(entity_ref)
        
        fields: dict[str, Any] = raw.get("fields", {})

        good: list[tuple[str, FieldResult]] = []
        bad: list[tuple[str, FieldResult]] = []

        for field_path, field_value in fields.items():
            source_system = None
            signal_id = None
            value = field_value

            # Support rich field dicts: {"value": ..., "source_system": ..., "signal_id": ...}
            if isinstance(field_value, dict) and "value" in field_value:
                value = field_value["value"]
                source_system = field_value.get("source_system")
                signal_id = field_value.get("signal_id")

            # Deep copy value before passing to rules to prevent rule mutations
            value_copy = copy.deepcopy(value)
            failures = self._run_field_rules(field_path, value_copy, raw, ctx)
            
            # Deep copy all data for storage to prevent external mutations of results
            value_for_storage = copy.deepcopy(value)
            source_system_copy = copy.deepcopy(source_system) if source_system is not None else None
            signal_id_copy = copy.deepcopy(signal_id) if signal_id is not None else None
            
            fr = FieldResult(
                field_path=field_path,
                value=value_for_storage,  # Store deep copy to ensure immutability
                source_system=source_system_copy,  # Store deep copy to ensure immutability
                signal_id=signal_id_copy,  # Store deep copy to ensure immutability
                failures=tuple(failures),
            )

            if failures:
                bad.append((field_path, fr))
            else:
                good.append((field_path, fr))

        # Deep copy raw entity before passing to entity rules
        raw_copy = copy.deepcopy(raw)
        entity_findings = self._run_entity_rules(raw_copy, ctx)

        result = EntityResult(
            entity_ref=MappingProxyType(entity_ref_copy),  # Use deep copy, not view of original
            entity_type=ctx.entity_type,
            good=tuple(good),
            bad=tuple(bad),
            entity_findings=tuple(entity_findings),
        )
        
        # Emit entity processed event
        duration_ms = (time.perf_counter() - start_time) * 1000
        self._hooks.emit_entity_processed(EntityProcessedEvent(
            timestamp=time.perf_counter(),
            entity_type=ctx.entity_type,
            ruleset_id=ctx.ruleset_id,
            entity_ref=MappingProxyType(entity_ref_copy),  # Use deep copy for consistency
            result=result,
            duration_ms=duration_ms,
        ))
        
        return result

    def _run_field_rules(
        self,
        field_path: str,
        value: Any,
        raw_entity: dict[str, Any],
        ctx: EvaluationContext,
    ) -> list[Finding]:
        """Execute all applicable field-scope rules."""
        failures: list[Finding] = []
        
        # Pre-compute context hash if caching is enabled
        ctx_hash = None
        if self._cache:
            ctx_hash = hash_context(ctx.entity_type, ctx.ruleset_id, ctx.reference_data)
        
        for rule in self._field_rules:
            if not self._rule_applies(rule, ctx.entity_type):
                continue
            if rule.field_path != field_path and rule.field_path != "*":
                continue
            
            finding = self._execute_rule_with_cache(rule, value, ctx, ctx_hash)
            
            if not finding.passed:
                failures.append(finding)
        
        return failures

    def _run_entity_rules(
        self, raw: dict[str, Any], ctx: EvaluationContext
    ) -> list[Finding]:
        """Execute all applicable entity-scope rules."""
        findings: list[Finding] = []
        
        # Pre-compute context hash if caching is enabled
        ctx_hash = None
        if self._cache:
            ctx_hash = hash_context(ctx.entity_type, ctx.ruleset_id, ctx.reference_data)
        
        for rule in self._entity_rules:
            if not self._rule_applies(rule, ctx.entity_type):
                continue
            
            finding = self._execute_rule_with_cache(rule, raw, ctx, ctx_hash)
            findings.append(finding)
        
        return findings

    def _evaluate_collection(
        self, raw_entities: list[dict[str, Any]], ctx: EvaluationContext
    ) -> list[Finding]:
        """Execute all applicable collection-scope rules."""
        findings: list[Finding] = []
        
        # Pre-compute context hash if caching is enabled
        ctx_hash = None
        if self._cache:
            ctx_hash = hash_context(ctx.entity_type, ctx.ruleset_id, ctx.reference_data)
        
        # Deep copy raw_entities before passing to collection rules to prevent mutations
        raw_entities_copy = copy.deepcopy(raw_entities)
        
        for rule in self._collection_rules:
            if not self._rule_applies(rule, ctx.entity_type):
                continue
            
            finding = self._execute_rule_with_cache(rule, raw_entities_copy, ctx, ctx_hash)
            findings.append(finding)
        
        return findings
    
    def _execute_rule_with_cache(
        self,
        rule: "Rule",
        target: Any,
        ctx: EvaluationContext,
        ctx_hash: Optional[str],
    ) -> Finding:
        """
        Execute a rule with optional caching.
        
        Checks cache first if enabled, executes rule if cache miss,
        and emits lifecycle events.
        """
        start_time = time.perf_counter()
        
        # Try cache if enabled
        if self._cache and ctx_hash:
            cache_key = make_cache_key(rule.rule_id, target, ctx_hash)
            cached_finding = self._cache.get(cache_key)
            
            if cached_finding is not None:
                # Cache hit - emit event and return
                duration_ms = (time.perf_counter() - start_time) * 1000
                self._hooks.emit_rule_execution(RuleExecutionEvent(
                    timestamp=time.perf_counter(),
                    entity_type=ctx.entity_type,
                    ruleset_id=ctx.ruleset_id,
                    rule_id=rule.rule_id,
                    scope=rule.scope.value,
                    duration_ms=duration_ms,
                    finding=cached_finding,
                ))
                return cached_finding
        
        # Cache miss or caching disabled - evaluate rule
        finding = safe_evaluate_rule(rule, target, ctx)
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # Store in cache if enabled
        if self._cache and ctx_hash:
            cache_key = make_cache_key(rule.rule_id, target, ctx_hash)
            self._cache.put(cache_key, finding)
        
        # Emit rule execution event
        self._hooks.emit_rule_execution(RuleExecutionEvent(
            timestamp=time.perf_counter(),
            entity_type=ctx.entity_type,
            ruleset_id=ctx.ruleset_id,
            rule_id=rule.rule_id,
            scope=rule.scope.value,
            duration_ms=duration_ms,
            finding=finding,
        ))
        
        return finding

    @staticmethod
    def _rule_applies(rule: "Rule", entity_type: str) -> bool:
        return "*" in rule.applies_to or entity_type in rule.applies_to
