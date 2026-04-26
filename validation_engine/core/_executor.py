"""
Rule execution mechanics.

Pure module-level helpers that take a ``Rule`` plus its inputs and produce
a ``RuleResult``. Kept separate from the engine class so the orchestration
(in ``engine.py``) reads at one level of abstraction.
"""
from __future__ import annotations

import copy
import time
from dataclasses import replace
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from ..models.enums import RuleExecutionStatus, Scope
from ..models.error import ValidationError
from ..models.finding import ValidationFinding
from ..models.rule_result import RuleResult
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


def skipped_result(rule: Rule) -> RuleResult:
    return RuleResult(
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        status=RuleExecutionStatus.SKIPPED,
        scope=rule.scope,
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
    yield (
        target,
        ctx.scoped(rule_id=rule.rule_id),
        None,
        None,
        {"entities": len(entities)},
    )


def _entity_targets(rule, entities, ctx):
    for entity in entities:
        entity_ref = entity.get("entity_ref", {}) or {}
        entity_copy = copy.deepcopy(entity)
        yield (
            entity_copy,
            ctx.scoped(rule_id=rule.rule_id, entity=entity_copy),
            entity_ref,
            None,
            {"entity_ref": dict(entity_ref)},
        )


def _field_targets(rule, entities, ctx):
    target_field = rule.field_path
    for entity in entities:
        raw_fields = entity.get("fields", {}) if isinstance(entity, dict) else {}
        # Skip entities the rule doesn't apply to *before* paying for deepcopy.
        if target_field == "*":
            if not raw_fields:
                continue
        elif target_field not in raw_fields:
            continue

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
                ctx.scoped(rule_id=rule.rule_id, entity=entity_copy, field_path=fpath),
                entity_ref,
                fpath,
                {"field_path": fpath, "entity_ref": dict(entity_ref)},
            )


# ----------------------------------------------------------------------
# runner
# ----------------------------------------------------------------------

def _run(rule, target_iter, errors):
    """Drive one rule through a stream of targets, producing one RuleResult."""
    findings: list[ValidationFinding] = []
    evaluated = passed = failed = 0
    t0 = time.perf_counter()
    for target, scoped_ctx, entity_ref, field_path, error_context in target_iter:
        try:
            rule_findings = _coerce_findings(
                rule.evaluate(target, scoped_ctx), rule, entity_ref, field_path,
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
                findings, evaluated, passed, failed, t0, error=err,
            )
        for finding in rule_findings:
            findings.append(finding)
            evaluated += 1
            if finding.passed:
                passed += 1
            else:
                failed += 1
    status = RuleExecutionStatus.PASSED if failed == 0 else RuleExecutionStatus.FAILED
    return _build_result(rule, status, findings, evaluated, passed, failed, t0)


def _build_result(
    rule: Rule,
    status: RuleExecutionStatus,
    findings: list[ValidationFinding],
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
        evaluated_count=evaluated,
        passed_count=passed,
        failed_count=failed,
        duration_ms=_elapsed(t0),
        error=error,
    )


def _coerce_findings(
    rv: Any,
    rule: Rule,
    entity_ref: Mapping[str, Any] | None,
    field_path: str | None,
) -> list[ValidationFinding]:
    """
    Normalize a rule's return value to ``list[ValidationFinding]``.

    Raises ``TypeError`` if the rule returned anything other than ``None``,
    a single ``ValidationFinding``, or an iterable of ``ValidationFinding``.
    Surfacing rule-author bugs is preferable to silently dropping output.
    """
    if rv is None:
        return []
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
    out: list[ValidationFinding] = []
    for f in candidates:
        updates: dict[str, Any] = {}
        if entity_ref and not f.entity_ref:
            updates["entity_ref"] = MappingProxyType(dict(entity_ref))
        if field_path and f.field_path is None:
            updates["field_path"] = field_path
        out.append(replace(f, **updates) if updates else f)
    return out


def _elapsed(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000
