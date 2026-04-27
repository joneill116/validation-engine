"""
ThresholdPolicy — graduated severity bands for numeric metrics.

Validation is rarely binary in practice. A NAV difference of 0.01 might
be a warning; 1.00 might be blocking; 1000 might be fatal. ``ThresholdPolicy``
models that vocabulary in a way standard rules can consume.

Bands are ordered most-severe-first when classifying — the highest-
severity matching band wins. ``Decimal`` is used end-to-end so float
drift can't change a borderline classification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Iterable, Sequence

from .enums import Severity


_SEVERITY_ORDER = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
    Severity.BLOCKING: 3,
    Severity.FATAL: 4,
}


class ThresholdMode(str, Enum):
    ABSOLUTE = "absolute"
    RELATIVE = "relative"
    PERCENTAGE = "percentage"


class ThresholdOperator(str, Enum):
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EQ = "eq"
    NEQ = "neq"


@dataclass(frozen=True)
class ThresholdBand:
    severity: Severity
    operator: ThresholdOperator
    value: Decimal
    mode: ThresholdMode = ThresholdMode.ABSOLUTE
    message: str | None = None

    def __post_init__(self) -> None:
        # Coerce string forms (often from YAML).
        if not isinstance(self.severity, Severity):
            object.__setattr__(self, "severity", Severity(self.severity))
        if not isinstance(self.operator, ThresholdOperator):
            object.__setattr__(self, "operator", ThresholdOperator(self.operator))
        if not isinstance(self.mode, ThresholdMode):
            object.__setattr__(self, "mode", ThresholdMode(self.mode))
        if not isinstance(self.value, Decimal):
            object.__setattr__(self, "value", Decimal(str(self.value)))

    def matches(self, metric_value: Decimal) -> bool:
        op = self.operator
        if op is ThresholdOperator.GT:
            return metric_value > self.value
        if op is ThresholdOperator.GTE:
            return metric_value >= self.value
        if op is ThresholdOperator.LT:
            return metric_value < self.value
        if op is ThresholdOperator.LTE:
            return metric_value <= self.value
        if op is ThresholdOperator.EQ:
            return metric_value == self.value
        if op is ThresholdOperator.NEQ:
            return metric_value != self.value
        raise ValueError(f"unsupported threshold operator: {op!r}")


@dataclass(frozen=True)
class ThresholdPolicy:
    policy_id: str
    metric_name: str
    bands: tuple[ThresholdBand, ...]
    unit: str | None = None

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("ThresholdPolicy.policy_id is required")
        if not self.metric_name:
            raise ValueError("ThresholdPolicy.metric_name is required")
        if not isinstance(self.bands, tuple):
            object.__setattr__(self, "bands", tuple(self.bands))
        if not self.bands:
            raise ValueError("ThresholdPolicy must have at least one band")

    def classify(self, metric_value: Decimal) -> Severity | None:
        """
        Return the most-severe matching band's severity, or None if none match.

        Bands are evaluated in order; ties broken by severity ordering
        (FATAL > BLOCKING > ERROR > WARNING > INFO).
        """
        if not isinstance(metric_value, Decimal):
            metric_value = Decimal(str(metric_value))
        matched = [b for b in self.bands if b.matches(metric_value)]
        if not matched:
            return None
        return max(matched, key=lambda b: _SEVERITY_ORDER[b.severity]).severity

    def matching_band(self, metric_value: Decimal) -> ThresholdBand | None:
        """Like ``classify`` but returns the band itself (for messages)."""
        if not isinstance(metric_value, Decimal):
            metric_value = Decimal(str(metric_value))
        matched = [b for b in self.bands if b.matches(metric_value)]
        if not matched:
            return None
        return max(matched, key=lambda b: _SEVERITY_ORDER[b.severity])
