"""
ValidationEngine — orchestrates rule execution against a ValidationRequest.

Contract::

    ValidationRequest
        -> ValidationEngine
            -> RuleResult (one per rule)
            -> ValidationFinding (zero or more per rule)
            -> ValidationSummary (aggregated)
            -> ValidationDecision (from strategy)
        -> ValidationResult

The engine is intentionally generic. It does not know about queues,
storage, schemas, or any business domain.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping

from ..models.enums import Scope, ValidationStatus
from ..models.error import ValidationError
from ..models.partition_decision import PartitionDecision
from ..models.request import ValidationRequest
from ..models.result import ValidationResult
from ..models.rule_result import RuleResult
from ..models.summary import ValidationSummary
from ..rules.base import Rule
from ..strategies.base import PerPartitionStrategy, PublishStrategy
from ..strategies.severity_gate import SeverityGateStrategy
from ..registries.rule_registry import RuleRegistry
from ..registries.strategy_registry import StrategyRegistry
from . import _executor
from .context import EvaluationContext

logger = logging.getLogger(__name__)


class PayloadValidationError(ValueError):
    """Raised when the request's payload structure is malformed."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_payload(payload: Any) -> list[dict[str, Any]]:
    """Validate the payload shape and return its entities list."""
    if not isinstance(payload, dict):
        raise PayloadValidationError(
            f"payload must be a mapping, got {type(payload).__name__}"
        )
    entities = payload.get("entities")
    if entities is None:
        raise PayloadValidationError("payload missing 'entities' key")
    if not isinstance(entities, list):
        raise PayloadValidationError(
            f"payload['entities'] must be a list, got {type(entities).__name__}"
        )
    for idx, entity in enumerate(entities):
        if not isinstance(entity, dict):
            raise PayloadValidationError(
                f"payload['entities'][{idx}] must be a mapping, got {type(entity).__name__}"
            )
        if "fields" in entity and not isinstance(entity["fields"], dict):
            raise PayloadValidationError(
                f"payload['entities'][{idx}]['fields'] must be a mapping, "
                f"got {type(entity['fields']).__name__}"
            )
        if "entity_ref" in entity and not isinstance(entity["entity_ref"], dict):
            raise PayloadValidationError(
                f"payload['entities'][{idx}]['entity_ref'] must be a mapping, "
                f"got {type(entity['entity_ref']).__name__}"
            )
    return entities


def _resolve_request(
    request: ValidationRequest | None,
    *,
    payload: Mapping[str, Any] | None,
    entity_type: str | None,
    ruleset_id: str | None,
    ruleset_version: str | None,
    metadata: Mapping[str, Any] | None,
) -> ValidationRequest:
    """
    Either return the supplied ``request`` or build one from kwargs.

    Rejects passing both a ``request`` and request-shaped kwargs together
    — that combination is almost always a mistake.
    """
    request_kwargs = (payload, entity_type, ruleset_id, ruleset_version, metadata)
    if request is None:
        if payload is None or entity_type is None or ruleset_id is None:
            raise ValueError(
                "validate() requires either a ValidationRequest or "
                "payload+entity_type+ruleset_id keyword arguments"
            )
        return ValidationRequest(
            payload=dict(payload),
            entity_type=entity_type,
            ruleset_id=ruleset_id,
            ruleset_version=ruleset_version or "latest",
            metadata=metadata or {},
        )
    if any(v is not None for v in request_kwargs):
        raise ValueError(
            "validate() received both a ValidationRequest and request-shaped "
            "keyword arguments (payload/entity_type/ruleset_id/ruleset_version/"
            "metadata); pass one or the other."
        )
    return request


class ValidationEngine:
    """
    Orchestrates a validation run.

    Two construction modes:

    1. Direct rules and strategy::

        engine = ValidationEngine(rules=[...], strategy=...)

    2. Registry-driven (resolve at validate-time)::

        engine = ValidationEngine.from_registries(
            rule_registry=rr, strategy_registry=sr,
        )
        result = engine.validate(request, strategy_id="severity_gate")
    """

    def __init__(
        self,
        rules: list[Rule] | None = None,
        strategy: PublishStrategy | None = None,
        *,
        reference_data: Mapping[str, Any] | None = None,
        rule_registry: RuleRegistry | None = None,
        strategy_registry: StrategyRegistry | None = None,
    ) -> None:
        self._rules: list[Rule] = list(rules or [])
        self._strategy: PublishStrategy | None = strategy
        self._reference_data: MappingProxyType = MappingProxyType(dict(reference_data or {}))
        self._rule_registry = rule_registry
        self._strategy_registry = strategy_registry

    @classmethod
    def from_registries(
        cls,
        rule_registry: RuleRegistry,
        strategy_registry: StrategyRegistry,
        reference_data: Mapping[str, Any] | None = None,
    ) -> "ValidationEngine":
        return cls(
            reference_data=reference_data,
            rule_registry=rule_registry,
            strategy_registry=strategy_registry,
        )

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def validate(
        self,
        request: ValidationRequest | None = None,
        *,
        # backwards-compat keyword arguments
        payload: Mapping[str, Any] | None = None,
        entity_type: str | None = None,
        ruleset_id: str | None = None,
        ruleset_version: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        strategy_id: str | None = None,
    ) -> ValidationResult:
        """
        Run validation and return a ``ValidationResult``.

        Preferred form::

            engine.validate(request)

        Backwards-compatible form (auto-builds a ValidationRequest)::

            engine.validate(payload=..., entity_type=..., ruleset_id=...)
        """
        request = _resolve_request(
            request,
            payload=payload,
            entity_type=entity_type,
            ruleset_id=ruleset_id,
            ruleset_version=ruleset_version,
            metadata=metadata,
        )

        # Resolve everything that could fail (payload shape, registry lookups,
        # strategy resolution) before we start the run. Failures here are
        # configuration / input errors and shouldn't pollute the run log.
        entities = _validate_payload(request.payload)
        rules = self._resolve_rules(request)
        strategy = self._resolve_strategy(strategy_id)

        return self._run(request, entities, rules, strategy)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _run(
        self,
        request: ValidationRequest,
        entities: list[dict[str, Any]],
        rules: list[Rule],
        strategy: PublishStrategy,
    ) -> ValidationResult:
        """Execute the resolved rules and assemble a ValidationResult."""
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        started_at = _utc_now()
        t0 = time.perf_counter()
        logger.info(
            "Validation start: run_id=%s request_id=%s entity_type=%s ruleset_id=%s",
            run_id, request.request_id, request.entity_type, request.ruleset_id,
        )

        ctx = EvaluationContext(
            request=request,
            ruleset_id=request.ruleset_id,
            ruleset_version=request.ruleset_version,
            reference_data=self._reference_data,
        )

        rule_results, errors = self._execute_rules(rules, request.entity_type, entities, ctx)
        findings = tuple(f for r in rule_results for f in r.findings)
        summary = ValidationSummary.from_results(
            rule_results=rule_results,
            findings=findings,
            total_entities_evaluated=len(entities),
        )
        decision = strategy.decide(findings, errors, summary)
        partition_decisions = self._decide_partitions(
            strategy, rule_results, errors, summary, entities,
        )
        status = self._determine_status(summary, errors)

        completed_at = _utc_now()
        duration_ms = (time.perf_counter() - t0) * 1000

        result = ValidationResult(
            validation_run_id=run_id,
            request_id=request.request_id,
            status=status,
            summary=summary,
            decision=decision,
            findings=findings,
            rule_results=tuple(rule_results),
            errors=tuple(errors),
            partition_decisions=partition_decisions,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )

        logger.info(
            "Validation complete: run_id=%s status=%s decision=%s findings=%d errors=%d duration_ms=%.2f",
            run_id, status.value, decision.action.value, len(findings), len(errors), duration_ms,
        )
        return result

    @staticmethod
    def _execute_rules(
        rules: list[Rule],
        entity_type: str,
        entities: list[dict[str, Any]],
        ctx: EvaluationContext,
    ) -> tuple[list[RuleResult], list[ValidationError]]:
        rule_results: list[RuleResult] = []
        errors: list[ValidationError] = []
        for rule in rules:
            if not _executor.rule_applies(rule, entity_type):
                rule_results.append(_executor.skipped_result(rule))
                continue
            rule_results.append(_executor.execute_rule(rule, entities, ctx, errors))
        return rule_results, errors

    def _resolve_rules(self, request: ValidationRequest) -> list[Rule]:
        if self._rule_registry is not None:
            return self._rule_registry.get(request.entity_type, request.ruleset_id)
        return list(self._rules)

    def _resolve_strategy(self, strategy_id: str | None) -> PublishStrategy:
        if strategy_id is not None:
            if self._strategy_registry is None:
                raise ValueError(
                    "strategy_id was provided but engine has no strategy_registry; "
                    "construct with from_registries(...) to enable strategy lookup."
                )
            return self._strategy_registry.get(strategy_id)
        if self._strategy is not None:
            return self._strategy
        if self._strategy_registry is not None:
            raise ValueError(
                "engine has a strategy_registry but no strategy_id was provided; "
                "pass strategy_id=... to validate()."
            )
        return SeverityGateStrategy()

    @staticmethod
    def _determine_status(
        summary: ValidationSummary,
        errors: list[ValidationError],
    ) -> ValidationStatus:
        if errors:
            return ValidationStatus.ERROR
        if summary.blocking_count > 0:
            return ValidationStatus.FAILED
        if summary.warning_count > 0:
            return ValidationStatus.PASSED_WITH_WARNINGS
        return ValidationStatus.PASSED

    @staticmethod
    def _decide_partitions(
        strategy: PublishStrategy,
        rule_results: list[RuleResult],
        errors: list[ValidationError],
        summary: ValidationSummary,
        entities: list[dict[str, Any]],
    ) -> tuple[PartitionDecision, ...]:
        """If the strategy is partition-aware, ask it for per-slice decisions."""
        if not isinstance(strategy, PerPartitionStrategy):
            return ()
        # Pre-filter to entity/field-scope findings. Collection-scope findings
        # don't belong to any specific entity, so the partition strategy must
        # not see them (otherwise it can't tell "no entity" apart from
        # "entity with empty entity_ref").
        entity_scope_findings = tuple(
            f for r in rule_results
            for f in r.findings
            if r.scope is not Scope.COLLECTION
        )
        return strategy.decide_per_partition(
            entity_scope_findings, errors, summary, tuple(entities),
        )
