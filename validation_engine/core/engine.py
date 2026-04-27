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
import platform
import time
import uuid
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping

from ..models.enums import Scope, ValidationStatus
from ..models.error import ValidationError
from ..models.manifest import ValidationManifest
from ..models.outcome import ValidationOutcome
from ..models.partition_decision import PartitionDecision
from ..models.plan import PlannedRule, ValidationPlan, make_plan_id
from ..models.request import ValidationRequest
from ..models.result import ValidationResult
from ..models.rule_result import RuleResult
from ..models.summary import ValidationSummary
from .contract_rules import synthesize_contract_rules
from .hashing import stable_hash
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


def _topological_order(rules: list[Rule]) -> list[Rule]:
    """
    Return ``rules`` ordered so dependencies precede their dependents.

    Rules whose dependencies aren't present in the input list are treated
    as having zero dependencies (the dependency check at run-time will
    handle the missing-prereq case). The compiler already validates the
    graph, so cycles never reach this point.
    """
    by_id: dict[str, Rule] = {r.rule_id: r for r in rules}
    visited: set[str] = set()
    order: list[Rule] = []

    def visit(rule: Rule) -> None:
        if rule.rule_id in visited:
            return
        for dep in getattr(rule, "depends_on", ()):
            target = by_id.get(dep.rule_id)
            if target is not None:
                visit(target)
        visited.add(rule.rule_id)
        order.append(rule)

    for rule in rules:
        visit(rule)
    return order


def _check_dependencies(
    rule: Rule,
    results_by_id: Mapping[str, RuleResult],
) -> str | None:
    """
    Return a skip reason if ``rule`` should not run because of its deps.

    ``None`` means the rule is free to run.
    """
    from ..models.dependency import DependencyMode
    from ..models.enums import RuleExecutionStatus

    for dep in getattr(rule, "depends_on", ()):
        prior = results_by_id.get(dep.rule_id)
        if prior is None:
            # Compiler enforces presence within a single ruleset, but a
            # dependency on a rule that the registry didn't include in
            # this run still happens. Treat as "dependency unmet".
            return f"dependency_missing:{dep.rule_id}"
        if dep.mode is DependencyMode.REQUIRES_PASS:
            if prior.status is not RuleExecutionStatus.PASSED:
                return f"dependency_failed:{dep.rule_id}"
        elif dep.mode is DependencyMode.REQUIRES_RUN:
            # ERROR / SKIPPED / NOT_APPLICABLE all count as "didn't run".
            if prior.status not in (
                RuleExecutionStatus.PASSED, RuleExecutionStatus.FAILED,
            ):
                return f"dependency_did_not_run:{dep.rule_id}"
        elif dep.mode is DependencyMode.SKIP_IF_FAILED:
            if prior.status in (
                RuleExecutionStatus.FAILED, RuleExecutionStatus.ERROR,
            ):
                return f"dependency_failed:{dep.rule_id}"
    return None


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
        engine_version: str | None = None,
    ) -> None:
        self._rules: list[Rule] = list(rules or [])
        self._strategy: PublishStrategy | None = strategy
        self._reference_data: MappingProxyType = MappingProxyType(dict(reference_data or {}))
        self._rule_registry = rule_registry
        self._strategy_registry = strategy_registry
        # Recorded into the manifest for replay/diagnostics.
        from .. import __version__ as _pkg_version
        self.engine_version = engine_version or _pkg_version
        self._python_version = platform.python_version()

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
        # Append synthetic rules derived from the contract snapshot (if
        # any). They go through the executor exactly like user rules and
        # show up in summary aggregations under stable ``_contract.``
        # rule_ids.
        if request.contract_snapshot is not None:
            rules = list(rules) + synthesize_contract_rules(request.contract_snapshot)
        strategy = self._resolve_strategy(strategy_id)

        # Profile-level pre-flight checks: if the request supplied a
        # ValidationProfile, surface mismatches between the profile's
        # expectations and the actual inputs *as runtime errors* (not
        # findings) — they're configuration problems, not data problems.
        pre_errors: list[ValidationError] = self._validate_profile_expectations(request)

        return self._run(request, entities, rules, strategy, pre_errors=pre_errors)

    def plan(
        self,
        request: ValidationRequest | None = None,
        *,
        payload: Mapping[str, Any] | None = None,
        entity_type: str | None = None,
        ruleset_id: str | None = None,
        ruleset_version: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ValidationPlan:
        """
        Return a ``ValidationPlan`` describing what ``validate(request)`` would do.

        The plan is a read-only preview: it does not call any rule. Use
        it to surface the resolved ruleset, applicability, dependency
        graph, and required reference data before paying for a real run.
        """
        request = _resolve_request(
            request,
            payload=payload, entity_type=entity_type,
            ruleset_id=ruleset_id, ruleset_version=ruleset_version,
            metadata=metadata,
        )
        rules = self._resolve_rules(request)
        planned: list[PlannedRule] = []
        for rule in rules:
            target_dict: dict[str, Any] = {"scope": rule.scope.value}
            if rule.field_path and rule.field_path != "*":
                target_dict["field_path"] = rule.field_path
            planned.append(PlannedRule(
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                rule_type=getattr(rule, "rule_type", type(rule).__name__),
                scope=rule.scope.value,
                severity=rule.severity.value,
                category=rule.category.value,
                field_path=rule.field_path if rule.field_path != "*" else None,
                group_id=getattr(rule, "group_id", None),
                enabled=True,
                dependencies=tuple(d.rule_id for d in getattr(rule, "depends_on", ())),
                has_applicability=not getattr(rule, "applies_when", None) or not rule.applies_when.is_unconditional,
                target=target_dict,
            ))
        required_refs = tuple(sorted(request.reference_data_snapshots.keys()))
        contract = request.contract_snapshot
        return ValidationPlan(
            plan_id=make_plan_id(),
            request_id=request.request_id,
            ruleset_id=request.ruleset_id,
            ruleset_version=request.ruleset_version,
            contract_id=contract.contract_id if contract else None,
            contract_version=contract.contract_version if contract else None,
            planned_rules=tuple(planned),
            required_reference_data=required_refs,
        )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_profile_expectations(request: ValidationRequest) -> list[ValidationError]:
        """
        Surface profile/contract/reference-data mismatches as runtime errors.

        These are *configuration* errors, not data-quality issues — the
        run was set up wrong, not the payload. They land on
        ``result.errors`` and the outcome promotes to ERROR.
        """
        profile = request.profile
        if profile is None:
            return []
        out: list[ValidationError] = []

        # Expected contract identity must match the supplied snapshot.
        if profile.expected_contract_id is not None:
            cs = request.contract_snapshot
            if cs is None:
                out.append(ValidationError(
                    error_type="ProfileExpectationUnmet",
                    message=(
                        f"profile {profile.profile_id!r} expects contract "
                        f"{profile.expected_contract_id!r} but the request "
                        f"supplied no contract_snapshot"
                    ),
                    context={"profile_id": profile.profile_id},
                ))
            elif cs.contract_id != profile.expected_contract_id:
                out.append(ValidationError(
                    error_type="ProfileExpectationUnmet",
                    message=(
                        f"profile {profile.profile_id!r} expects contract_id "
                        f"{profile.expected_contract_id!r}, got {cs.contract_id!r}"
                    ),
                    context={
                        "profile_id": profile.profile_id,
                        "expected_contract_id": profile.expected_contract_id,
                        "actual_contract_id": cs.contract_id,
                    },
                ))
            elif (
                profile.expected_contract_version is not None
                and cs.contract_version != profile.expected_contract_version
            ):
                out.append(ValidationError(
                    error_type="ProfileExpectationUnmet",
                    message=(
                        f"profile {profile.profile_id!r} expects contract_version "
                        f"{profile.expected_contract_version!r}, got {cs.contract_version!r}"
                    ),
                    context={
                        "profile_id": profile.profile_id,
                        "expected_contract_version": profile.expected_contract_version,
                        "actual_contract_version": cs.contract_version,
                    },
                ))

        # Required reference data names must all be supplied.
        supplied_refs = set(request.reference_data_snapshots.keys())
        for required_name in profile.required_reference_data:
            if required_name not in supplied_refs:
                out.append(ValidationError(
                    error_type="ProfileExpectationUnmet",
                    message=(
                        f"profile {profile.profile_id!r} requires reference data "
                        f"{required_name!r} but it was not supplied"
                    ),
                    context={
                        "profile_id": profile.profile_id,
                        "missing_reference_data": required_name,
                    },
                ))
        return out

    def _merge_reference_data(self, request: ValidationRequest) -> dict[str, Any]:
        """Combine engine-level static reference data with request snapshots."""
        merged: dict[str, Any] = dict(self._reference_data)
        for name, snapshot in request.reference_data_snapshots.items():
            # Snapshot data is exposed at the snapshot's ``name``. Whether
            # ``data`` is a dict, list, or scalar is the caller's call —
            # the engine keeps it opaque and just makes it addressable
            # via ``ctx.get_reference_data(name)``.
            merged[name] = snapshot.data
        return merged

    def _build_manifest(
        self,
        *,
        run_id: str,
        request: ValidationRequest,
        rules: list[Rule],
        reference_data: Mapping[str, Any],
        started_at: datetime,
        completed_at: datetime,
    ) -> ValidationManifest:
        # Hash *only* the parts of the rule the engine treats as inputs.
        # Including class objects directly would make hashes unstable
        # across imports.
        rules_for_hash = [
            {
                "rule_id": r.rule_id,
                "rule_version": r.rule_version,
                "scope": r.scope.value,
                "severity": r.severity.value,
                "category": r.category.value,
                "field_path": r.field_path,
                "applies_to": sorted(r.applies_to),
                "group_id": getattr(r, "group_id", None),
                "depends_on": [
                    {"rule_id": d.rule_id, "mode": d.mode.value}
                    for d in getattr(r, "depends_on", ())
                ],
            }
            for r in rules
        ]
        ref_hashes: dict[str, str] = {}
        for name, snapshot in request.reference_data_snapshots.items():
            if snapshot.snapshot_hash is not None:
                ref_hashes[name] = snapshot.snapshot_hash
                continue
            data_for_hash: Any
            if isinstance(snapshot.data, Mapping):
                data_for_hash = dict(snapshot.data)
            else:
                data_for_hash = snapshot.data
            ref_hashes[name] = stable_hash({
                "name": snapshot.name,
                "version": snapshot.version,
                "data": data_for_hash,
            })
        contract_hash: str | None = None
        if request.contract_snapshot is not None:
            cs = request.contract_snapshot
            contract_hash = cs.contract_hash or stable_hash({
                "contract_id": cs.contract_id,
                "contract_version": cs.contract_version,
                "entity_type": cs.entity_type,
                "fields": [
                    {
                        "field_path": f.field_path,
                        "field_type": f.field_type,
                        "required": f.required,
                        "nullable": f.nullable,
                        "semantic_type": f.semantic_type,
                    }
                    for f in cs.fields
                ],
                "required_entity_ref_keys": list(cs.required_entity_ref_keys),
            })
        profile_hash: str | None = None
        if request.profile is not None:
            p = request.profile
            profile_hash = stable_hash({
                "profile_id": p.profile_id,
                "profile_version": p.profile_version,
                "ruleset_id": p.ruleset_id,
                "ruleset_version": p.ruleset_version,
                "expected_contract_id": p.expected_contract_id,
                "expected_contract_version": p.expected_contract_version,
                "required_reference_data": list(p.required_reference_data),
                "default_severity": p.default_severity.value,
                "default_category": p.default_category.value,
                "threshold_policy_ids": sorted(p.threshold_policies.keys()),
            })
        return ValidationManifest(
            validation_run_id=run_id,
            request_id=request.request_id,
            payload_hash=stable_hash(request.payload),
            ruleset_hash=stable_hash(rules_for_hash),
            contract_snapshot_hash=contract_hash,
            profile_hash=profile_hash,
            reference_data_hashes=ref_hashes,
            engine_version=self.engine_version,
            python_version=self._python_version,
            started_at=started_at,
            completed_at=completed_at,
        )

    def _run(
        self,
        request: ValidationRequest,
        entities: list[dict[str, Any]],
        rules: list[Rule],
        strategy: PublishStrategy,
        *,
        pre_errors: list[ValidationError] | None = None,
    ) -> ValidationResult:
        """Execute the resolved rules and assemble a ValidationResult."""
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        started_at = _utc_now()
        t0 = time.perf_counter()
        logger.info(
            "Validation start: run_id=%s request_id=%s entity_type=%s ruleset_id=%s",
            run_id, request.request_id, request.entity_type, request.ruleset_id,
        )

        # Reference data merges from two sources:
        #   1. The engine's static reference_data (provided at construction)
        #   2. The request's reference_data_snapshots (fresh per request)
        # Snapshot-style overrides win — they're the more specific input.
        reference_data = self._merge_reference_data(request)

        ctx = EvaluationContext(
            request=request,
            ruleset_id=request.ruleset_id,
            ruleset_version=request.ruleset_version,
            reference_data=reference_data,
        )

        rule_results, errors = self._execute_rules(rules, request.entity_type, entities, ctx)
        if pre_errors:
            # Profile pre-flight errors come before any rule executes;
            # they belong on the run-level error list.
            errors = list(pre_errors) + errors
        findings = tuple(f for r in rule_results for f in r.findings)
        observations = tuple(o for r in rule_results for o in r.observations)
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
        # Outcome should reflect *all* errors, including profile pre-flight
        # errors that don't correspond to any rule execution (and thus
        # don't show up in summary.error_count).
        outcome = ValidationOutcome.from_signals(
            warning_count=summary.warning_count,
            blocking_count=summary.blocking_count,
            error_count=max(summary.error_count, len(errors)),
        )

        completed_at = _utc_now()
        duration_ms = (time.perf_counter() - t0) * 1000

        manifest = self._build_manifest(
            run_id=run_id,
            request=request,
            rules=rules,
            reference_data=reference_data,
            started_at=started_at,
            completed_at=completed_at,
        )

        result = ValidationResult(
            validation_run_id=run_id,
            request_id=request.request_id,
            status=status,
            summary=summary,
            decision=decision,
            outcome=outcome,
            findings=findings,
            observations=observations,
            rule_results=tuple(rule_results),
            errors=tuple(errors),
            partition_decisions=partition_decisions,
            manifest=manifest,
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
        # Topologically order rules so that prerequisites run before their
        # dependents. The compiler already validated the graph so this is
        # safe (no cycles, no missing references).
        ordered = _topological_order(rules)
        results_by_id: dict[str, RuleResult] = {}

        for rule in ordered:
            if not _executor.rule_applies(rule, entity_type):
                skipped = _executor.skipped_result(rule)
                rule_results.append(skipped)
                results_by_id[rule.rule_id] = skipped
                continue

            # Dependency check.
            skip_reason = _check_dependencies(rule, results_by_id)
            if skip_reason is not None:
                skipped = _executor.skipped_result(rule, skip_reason=skip_reason)
                rule_results.append(skipped)
                results_by_id[rule.rule_id] = skipped
                continue

            result = _executor.execute_rule(rule, entities, ctx, errors)
            rule_results.append(result)
            results_by_id[rule.rule_id] = result
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
