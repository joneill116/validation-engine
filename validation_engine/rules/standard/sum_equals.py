"""
SumEqualsRule — collection-scope rule.

Asserts that the sum of one numeric field across the collection equals
a target value (constant or sourced from reference_data). Non-numeric
amounts produce a failed finding rather than being silently dropped.

Optionally a ``threshold_policy: <id>`` parameter can name a
``ThresholdPolicy`` registered on the request's ``ValidationProfile``.
When supplied, the policy's bands classify the absolute difference and
override both the rule's static severity and tolerance — useful for
graduated reconciliation (warning at 0.01, blocking at 1.00, fatal at
1000, etc.).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope, Severity
from ...models.finding import ValidationFinding
from ...models import finding_codes
from ..configured import ConfiguredRule
from ._helpers import extract_field, to_decimal


class SumEqualsRule(ConfiguredRule):
    rule_type = "sum_equals"
    finding_code = finding_codes.RECONCILIATION_BREAK

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
        # Optional threshold policy reference. Resolved at evaluate-time
        # against ``ctx.get_threshold_policy(...)`` so a single rule can
        # share a policy declared once on the profile.
        self.threshold_policy_id: str | None = self.params.get("threshold_policy")

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
        return [*bad_amounts, self._comparison_finding(total, expected, ctx)]

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
        self,
        total: Decimal,
        expected: Decimal | None,
        ctx: EvaluationContext,
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

        # When the rule names a threshold policy and the profile defines
        # it, the band classification overrides both static tolerance and
        # static severity. ``classify`` returns ``None`` for "no band
        # matched" — i.e. the diff is below every alert threshold.
        if self.threshold_policy_id is not None:
            policy = ctx.get_threshold_policy(self.threshold_policy_id)
            if policy is not None:
                band = policy.matching_band(diff)
                if band is None:
                    return self.make_finding(
                        passed=True,
                        message=self._message(
                            f"Sum of {self.amount_field!r} = {total}, expected "
                            f"{expected} (diff={diff}); within all "
                            f"{self.threshold_policy_id!r} thresholds"
                        ),
                        expected=str(expected),
                        actual=str(total),
                        evidence={
                            "diff": str(diff),
                            "threshold_policy": self.threshold_policy_id,
                        },
                    )
                # Band matched -> failed finding with band's severity.
                return self.make_finding(
                    passed=False,
                    severity=band.severity,
                    message=self._message(
                        band.message
                        or f"Sum of {self.amount_field!r} = {total}, expected "
                           f"{expected} (diff={diff}); breached "
                           f"{self.threshold_policy_id!r} band "
                           f"[{band.operator.value} {band.value}] "
                           f"-> severity={band.severity.value}"
                    ),
                    expected=str(expected),
                    actual=str(total),
                    evidence={
                        "diff": str(diff),
                        "threshold_policy": self.threshold_policy_id,
                        "band_operator": band.operator.value,
                        "band_value": str(band.value),
                    },
                )
            # threshold_policy_id was set but no policy is registered
            # under that name — fall through to flat tolerance and let
            # the missing policy show up in evidence so authors notice.

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
