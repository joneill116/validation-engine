"""
DateBetweenRule — asserts a date field is within an inclusive window.

The window can be sourced from rule params, reference data
(``ctx.reference_data``), or the request metadata. Window keys are
``start`` and ``end`` (ISO-8601 dates).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope
from ...models.finding import ValidationFinding
from ..configured import ConfiguredRule


def _to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None
    return None


class DateBetweenRule(ConfiguredRule):
    rule_type = "date_between"

    def __init__(self, rule_id: str, **kwargs) -> None:
        kwargs.setdefault("scope", Scope.FIELD)
        kwargs.setdefault("category", Category.BUSINESS)
        super().__init__(rule_id, **kwargs)
        self.window_ref: str | None = self.params.get("window_ref")
        self.start: str | None = self.params.get("start")
        self.end: str | None = self.params.get("end")
        if not self.window_ref and not (self.start and self.end):
            raise ValueError(
                f"DateBetweenRule {rule_id!r}: provide either 'window_ref' or both 'start' and 'end'"
            )

    def _resolve_window(self, ctx: EvaluationContext) -> tuple[date | None, date | None]:
        if self.window_ref:
            ref = ctx.reference_data.get(self.window_ref) if ctx.reference_data else None
            if isinstance(ref, dict):
                return _to_date(ref.get("start")), _to_date(ref.get("end"))
        return _to_date(self.start), _to_date(self.end)

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding:
        target_date = _to_date(target)
        start, end = self._resolve_window(ctx)
        if target_date is None:
            return self.make_finding(
                passed=False,
                message=self._message(
                    f"Field {self.field_path!r} is not a parseable date: {target!r}"
                ),
                    expected={"start": str(start), "end": str(end)},
                actual=target,
            )
        if start is None or end is None:
            return self.make_finding(
                passed=False,
                message=self._message(
                    "Date window not configured / not resolvable from reference data"
                ),
                    expected={"start": self.start, "end": self.end, "window_ref": self.window_ref},
                actual=target,
            )
        passed = start <= target_date <= end
        return self.make_finding(
            passed=passed,
            message=self._message(
                f"{target_date} not within window [{start}..{end}]"
            ) if not passed else f"{target_date} within window",
            expected={"start": str(start), "end": str(end)},
            actual=str(target_date),
        )
