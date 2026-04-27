"""
RecordCountRule — collection-scope assertion on record count.

Either ``min_count``, ``max_count``, or both. Emits an ``Observation``
recording the actual count regardless of pass/fail so dashboards can
trend record volume over time.
"""
from __future__ import annotations

from typing import Any

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope
from ...models.rule_evaluation import RuleEvaluation
from ..configured import ConfiguredRule


class RecordCountRule(ConfiguredRule):
    rule_type = "record_count"

    def __init__(self, rule_id: str, **kwargs) -> None:
        kwargs.setdefault("scope", Scope.COLLECTION)
        kwargs.setdefault("category", Category.STRUCTURAL)
        super().__init__(rule_id, **kwargs)
        self.min_count: int | None = self.params.get("min_count")
        self.max_count: int | None = self.params.get("max_count")
        if self.min_count is None and self.max_count is None:
            raise ValueError(
                f"RecordCountRule {rule_id!r}: provide 'min_count' or 'max_count'"
            )
        if (
            self.min_count is not None
            and self.max_count is not None
            and self.min_count > self.max_count
        ):
            raise ValueError(
                f"RecordCountRule {rule_id!r}: min_count > max_count "
                f"({self.min_count} > {self.max_count})"
            )

    def evaluate(self, target: Any, ctx: EvaluationContext) -> RuleEvaluation:
        entities = target if isinstance(target, list) else []
        count = len(entities)
        obs = self.observation("record_count", count, unit="records")

        below_min = self.min_count is not None and count < self.min_count
        above_max = self.max_count is not None and count > self.max_count
        if not below_min and not above_max:
            return self.passed(observations=[obs])

        bound_text = []
        if self.min_count is not None:
            bound_text.append(f"min={self.min_count}")
        if self.max_count is not None:
            bound_text.append(f"max={self.max_count}")
        finding = self.make_finding(
            passed=False,
            message=self._message(
                f"Record count {count} not within bounds [{', '.join(bound_text)}]"
            ),
            expected={"min": self.min_count, "max": self.max_count},
            actual=count,
            observation_ids=(obs.observation_id,),
        )
        return self.failed(finding, observations=[obs])
