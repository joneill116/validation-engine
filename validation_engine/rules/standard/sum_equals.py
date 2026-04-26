"""
SumEqualsRule — collection-scope rule.

Asserts that the sum of one numeric field across the collection equals
a target value (constant or sourced from reference_data). Non-numeric
amounts produce a failed finding rather than being silently dropped.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope
from ...models.finding import ValidationFinding
from ..configured import ConfiguredRule
from ._helpers import extract_field, to_decimal


class SumEqualsRule(ConfiguredRule):
    rule_type = "sum_equals"

    def __init__(self, rule_id: str, **kwargs) -> None:
        kwargs.setdefault("scope", Scope.COLLECTION)
        kwargs.setdefault("category", Category.CONSISTENCY)
        super().__init__(rule_id, **kwargs)
        self.amount_field: str | None = self.params.get("amount_field")
        if not self.amount_field:
            raise ValueError(
                f"SumEqualsRule {rule_id!r}: 'amount_field' is required"
            )
        self.expected_ref: str | None = self.params.get("expected_ref")
        if "expected_value" in self.params:
            try:
                self.expected_value: Decimal | None = to_decimal(self.params["expected_value"])
            except ValueError as exc:
                raise ValueError(
                    f"SumEqualsRule {rule_id!r}: invalid 'expected_value' "
                    f"{self.params['expected_value']!r}: {exc}"
                ) from exc
        else:
            self.expected_value = None
        if self.expected_value is None and not self.expected_ref:
            raise ValueError(
                f"SumEqualsRule {rule_id!r}: provide 'expected_value' or 'expected_ref'"
            )
        self.tolerance: Decimal = Decimal(str(self.params.get("tolerance", "0.01")))

    def _resolve_expected(self, ctx: EvaluationContext) -> Decimal | None:
        if self.expected_value is not None:
            return self.expected_value
        if self.expected_ref and ctx.reference_data:
            ref = ctx.reference_data.get(self.expected_ref)
            try:
                return to_decimal(ref)
            except ValueError:
                return None
        return None

    def evaluate(
        self, target: Any, ctx: EvaluationContext
    ) -> Iterable[ValidationFinding]:
        entities = target if isinstance(target, list) else []
        total, bad_amounts = self._sum_amounts(entities)
        expected = self._resolve_expected(ctx)
        return [*bad_amounts, self._comparison_finding(total, expected)]

    # ------------------------------------------------------------------

    def _sum_amounts(
        self, entities: list,
    ) -> tuple[Decimal, list[ValidationFinding]]:
        total = Decimal(0)
        bad_amounts: list[ValidationFinding] = []
        for entity in entities:
            fields = entity.get("fields", {}) if isinstance(entity, dict) else {}
            entity_ref = entity.get("entity_ref", {}) if isinstance(entity, dict) else {}
            raw = extract_field(fields, self.amount_field)
            if raw is None:
                continue
            try:
                total += to_decimal(raw)
            except ValueError as exc:
                bad_amounts.append(self.make_finding(
                    passed=False,
                    message=self._message(
                        f"Non-numeric {self.amount_field}={raw!r}: {exc}"
                    ),
                    expected="numeric",
                    actual=raw,
                    entity_ref=entity_ref if isinstance(entity_ref, dict) else None,
                    involved_fields=(self.amount_field,),
                ))
        return total, bad_amounts

    def _comparison_finding(
        self, total: Decimal, expected: Decimal | None,
    ) -> ValidationFinding:
        if expected is None:
            return self.make_finding(
                passed=False,
                message=self._message(
                    f"Could not resolve expected total from reference_data["
                    f"{self.expected_ref!r}]"
                ),
                expected=None,
                actual=str(total),
            )
        diff = abs(total - expected)
        passed = diff <= self.tolerance
        return self.make_finding(
            passed=passed,
            message=self._message(
                f"Sum of {self.amount_field!r} = {total}, expected {expected} (diff={diff})"
            ),
            expected=str(expected),
            actual=str(total),
            evidence={"diff": str(diff)},
        )
