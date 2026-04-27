"""
CompletenessRatioRule — collection-scope completeness check.

Asserts that the proportion of entities for which a given field is
populated meets a minimum ratio (default 1.0, i.e. fully complete).

Emits an ``Observation`` of the measured ratio whether the rule passes
or fails — completeness is a metric callers usually want to trend.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope
from ...models.rule_evaluation import RuleEvaluation
from ...models import finding_codes
from ..configured import ConfiguredRule
from ._helpers import extract_field


def _is_populated(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return True


class CompletenessRatioRule(ConfiguredRule):
    rule_type = "completeness_ratio"
    finding_code = finding_codes.COMPLETENESS_BELOW_THRESHOLD

    def __init__(self, rule_id: str, **kwargs) -> None:
        kwargs.setdefault("scope", Scope.COLLECTION)
        kwargs.setdefault("category", Category.COMPLETENESS)
        super().__init__(rule_id, **kwargs)
        self.target_field_path: str | None = self.params.get("field_path") or kwargs.get("field_path")
        if not self.target_field_path or self.target_field_path == "*":
            raise ValueError(
                f"CompletenessRatioRule {rule_id!r}: 'field_path' (in params or top-level) "
                f"is required"
            )
        self.min_ratio: Decimal = Decimal(str(self.params.get("min_ratio", "1.0")))
        if not (Decimal("0") <= self.min_ratio <= Decimal("1")):
            raise ValueError(
                f"CompletenessRatioRule {rule_id!r}: 'min_ratio' must be in [0, 1], "
                f"got {self.min_ratio}"
            )

    def evaluate(self, target: Any, ctx: EvaluationContext) -> RuleEvaluation:
        entities = target if isinstance(target, list) else []
        total = len(entities)
        populated = 0
        for entity in entities:
            fields = entity.get("fields", {}) if isinstance(entity, dict) else {}
            value = extract_field(fields, self.target_field_path)
            if _is_populated(value):
                populated += 1
        # Empty collection trivially satisfies the predicate. Treating it
        # as 0/0 = 1.0 lines up with the "no records means nothing
        # incomplete" interpretation downstream consumers expect.
        ratio = Decimal(populated) / Decimal(total) if total else Decimal("1")

        obs = self.observation(
            "completeness_ratio",
            str(ratio),
            unit="ratio",
            field_path=self.target_field_path,
            evidence={"populated": populated, "total": total},
        )
        if ratio >= self.min_ratio:
            return self.passed(observations=[obs])

        finding = self.make_finding(
            passed=False,
            message=self._message(
                f"Completeness for {self.target_field_path!r} = {ratio} "
                f"(populated={populated}/{total}); below min_ratio={self.min_ratio}"
            ),
            expected=f">={self.min_ratio}",
            actual=str(ratio),
            field_path=self.target_field_path,
            observation_ids=(obs.observation_id,),
        )
        return self.failed(finding, observations=[obs])
