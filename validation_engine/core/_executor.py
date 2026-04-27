"""
Rule execution mechanics.

Pure module-level helpers that take a ``Rule`` plus its inputs and produce
a ``RuleResult``. Kept separate from the engine class so the orchestration
(in ``engine.py``) reads at one level of abstraction.

Two rule API styles are supported:

  - Legacy positional: ``evaluate(self, target, ctx) -> Finding | Iterable[Finding]``
  - Context-only:      ``evaluate(self, ctx) -> RuleEvaluation``

The executor inspects the rule class once to decide which form to call,
then normalizes the return value to ``(findings, observations, status)``.
"""
from __future__ import annotations

import copy
import time
from dataclasses import replace
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from ..models.enums import RuleEvaluationStatus, RuleExecutionStatus, Scope
from ..models.error import ValidationError
from ..models.finding import ValidationFinding
from ..models.observation import Observation
from ..models.rule_evaluation import RuleEvaluation
from ..models.rule_result import RuleResult
from ..models.target import ValidationTarget
from ..rules.base import Rule
from .context import EvaluationContext


# A target tuple shape used between target-iterators and the runner:
#   (target, scoped_ctx, entity_ref, field_path, error_context)
# The shape stays a tuple rather than a dataclass to keep the hot path
# free of allocations beyond the deepcopy and context.scoped() calls
# that are unavoidable.


def rule_applies(rule: Rule, entity_type: str) -> bool:
    applies_to = rule.applies_to
    # Defend against a rule mis-declaring ``applies_to`` as a bare string,
    # which would silently substring-match entity_type.
    if isinstance(applies_to, str):
        applies_to = (applies_to,)
    return "*" in applies_to or entity_type in applies_to


def skipped_result(rule: Rule, *, skip_reason: str | None = None) -> RuleResult:
    return RuleResult(
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        status=RuleExecutionStatus.SKIPPED,
        scope=rule.scope,
        group_id=getattr(rule, "group_id", None),
        skip_reason=skip_reason,
    )


def execute_rule(
    rule: Rule,
    entities: list[dict[str, Any]],
    ctx: EvaluationContext,
    errors: list[ValidationError],
) -> RuleResult:
    """Execute one rule against the entities, capturing findings or an error."""
    return _run(rule, _targets_for_scope(rule, entities, ctx), errors)


# ----------------------------------------------------------------------
# target generators (one per scope)
# ----------------------------------------------------------------------

def _targets_for_scope(rule, entities, ctx):
    if rule.scope is Scope.COLLECTION:
        return _collection_targets(rule, entities, ctx)
    if rule.scope is Scope.ENTITY:
        return _entity_targets(rule, entities, ctx)
    return _field_targets(rule, entities, ctx)


def _collection_targets(rule, entities, ctx):
    target = copy.deepcopy(entities)
    # Collection rules don't have a single entity to predicate on. By
    # convention, ``applies_when`` is ignored at this scope (callers can
    # write a Python rule if they need a collection-level predicate).
    yield (
        target,
        ctx.scoped(
            rule_id=rule.rule_id,
            target=ValidationTarget.collection(),
        ),
        None,
        None,
        {"entities": len(entities)},
        True,  # applies_now
    )


def _entity_targets(rule, entities, ctx):
    applies_when = getattr(rule, "applies_when", None)
    for entity in entities:
        entity_ref = entity.get("entity_ref", {}) or {}
        fields = entity.get("fields", {}) if isinstance(entity, dict) else {}
        applies_now = True
        if applies_when is not None and not applies_when.is_unconditional:
            applies_now = applies_when.evaluate(fields)
        entity_copy = copy.deepcopy(entity)
        yield (
            entity_copy,
            ctx.scoped(
                rule_id=rule.rule_id,
                entity=entity_copy,
                entity_ref=entity_ref,
                target=ValidationTarget.entity(),
            ),
            entity_ref,
            None,
            {"entity_ref": dict(entity_ref)},
            applies_now,
        )


def _field_targets(rule, entities, ctx):
    target_field = rule.field_path
    applies_when = getattr(rule, "applies_when", None)
    for entity in entities:
        raw_fields = entity.get("fields", {}) if isinstance(entity, dict) else {}
        # Skip entities the rule doesn't apply to *before* paying for deepcopy.
        if target_field == "*":
            if not raw_fields:
                continue
        elif target_field not in raw_fields:
            continue

        applies_now = True
        if applies_when is not None and not applies_when.is_unconditional:
            applies_now = applies_when.evaluate(raw_fields)

        entity_ref = entity.get("entity_ref", {}) or {}
        entity_copy = copy.deepcopy(entity)
        fields = entity_copy.get("fields", {})
        items = (
            list(fields.items()) if target_field == "*"
            else [(target_field, fields[target_field])]
        )
        for fpath, raw in items:
            value = raw["value"] if isinstance(raw, dict) and "value" in raw else raw
            yield (
                value,
                ctx.scoped(
                    rule_id=rule.rule_id,
                    entity=entity_copy,
                    field_path=fpath,
                    field_value=value,
                    entity_ref=entity_ref,
                    target=ValidationTarget.field(fpath),
                ),
                entity_ref,
                fpath,
                {"field_path": fpath, "entity_ref": dict(entity_ref)},
                applies_now,
            )


# ----------------------------------------------------------------------
# runner
# ----------------------------------------------------------------------

def _run(rule, target_iter, errors):
    """Drive one rule through a stream of targets, producing one RuleResult."""
    findings: list[ValidationFinding] = []
    observations: list[Observation] = []
    evaluated = passed = failed = 0
    not_applicable_count = 0
    total_targets = 0
    takes_target = type(rule)._evaluate_takes_target()
    t0 = time.perf_counter()
    for target, scoped_ctx, entity_ref, field_path, error_context, applies_now in target_iter:
        total_targets += 1
        if not applies_now:
            # The rule's applies_when predicate evaluated false for this
            # specific target. Don't run the rule body — record a
            # not-applicable hit so the per-rule status can promote to
            # NOT_APPLICABLE if every target evaluated this way.
            not_applicable_count += 1
            continue
        try:
            rv = rule.evaluate(target, scoped_ctx) if takes_target else rule.evaluate(scoped_ctx)
            rule_findings, rule_observations, na = _normalize_return(
                rv, rule, entity_ref, field_path,
            )
        except Exception as exc:
            err = ValidationError.from_exception(
                exc,
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                context=error_context,
            )
            errors.append(err)
            return _build_result(
                rule, RuleExecutionStatus.ERROR,
                findings, observations, evaluated, passed, failed, t0, error=err,
            )
        observations.extend(rule_observations)
        if na:
            not_applicable_count += 1
            continue
        for finding in rule_findings:
            findings.append(finding)
            evaluated += 1
            if finding.passed:
                passed += 1
            else:
                failed += 1
    if total_targets > 0 and not_applicable_count == total_targets and evaluated == 0:
        # Every target reported NOT_APPLICABLE — surface that at the rule level.
        return _build_result(
            rule, RuleExecutionStatus.NOT_APPLICABLE,
            findings, observations, evaluated, passed, failed, t0,
        )
    status = RuleExecutionStatus.PASSED if failed == 0 else RuleExecutionStatus.FAILED
    return _build_result(rule, status, findings, observations, evaluated, passed, failed, t0)


def _build_result(
    rule: Rule,
    status: RuleExecutionStatus,
    findings: list[ValidationFinding],
    observations: list[Observation],
    evaluated: int,
    passed: int,
    failed: int,
    t0: float,
    *,
    error: ValidationError | None = None,
) -> RuleResult:
    return RuleResult(
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        status=status,
        scope=rule.scope,
        findings=tuple(findings),
        observations=tuple(observations),
        evaluated_count=evaluated,
        passed_count=passed,
        failed_count=failed,
        duration_ms=_elapsed(t0),
        error=error,
        group_id=getattr(rule, "group_id", None),
    )


def _normalize_return(
    rv: Any,
    rule: Rule,
    entity_ref: Mapping[str, Any] | None,
    field_path: str | None,
) -> tuple[list[ValidationFinding], list[Observation], bool]:
    """
    Normalize a rule's return value to ``(findings, observations, na_flag)``.

    Accepted shapes:
      - ``None``                         -> no findings
      - a single ``ValidationFinding``   -> [that finding]
      - an iterable of ``ValidationFinding``
      - a ``RuleEvaluation``             -> (findings, observations, na)

    Anything else raises ``TypeError`` so rule-author bugs surface.
    """
    if rv is None:
        return [], [], False
    if isinstance(rv, RuleEvaluation):
        if rv.status is RuleEvaluationStatus.NOT_APPLICABLE:
            return [], list(rv.observations), True
        findings = _stamp_default_context(list(rv.findings), entity_ref, field_path)
        return findings, list(rv.observations), False
    if isinstance(rv, ValidationFinding):
        candidates: list[ValidationFinding] = [rv]
    elif isinstance(rv, (str, bytes)) or not isinstance(rv, Iterable):
        raise TypeError(
            f"Rule {rule.rule_id!r} returned non-Finding value: {type(rv).__name__}"
        )
    else:
        candidates = list(rv)
        for item in candidates:
            if not isinstance(item, ValidationFinding):
                raise TypeError(
                    f"Rule {rule.rule_id!r} returned a non-Finding item: "
                    f"{type(item).__name__}"
                )
    return _stamp_default_context(candidates, entity_ref, field_path), [], False


def _stamp_default_context(
    findings: list[ValidationFinding],
    entity_ref: Mapping[str, Any] | None,
    field_path: str | None,
) -> list[ValidationFinding]:
    """Fill in entity_ref / field_path on findings that don't carry them."""
    out: list[ValidationFinding] = []
    for f in findings:
        updates: dict[str, Any] = {}
        if entity_ref and not f.entity_ref:
            updates["entity_ref"] = MappingProxyType(dict(entity_ref))
        if field_path and f.field_path is None:
            updates["field_path"] = field_path
        out.append(replace(f, **updates) if updates else f)
    return out


def _elapsed(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000
