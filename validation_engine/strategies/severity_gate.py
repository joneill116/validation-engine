"""
SeverityGateStrategy — default decision strategy.

Maps run signals to a ``ValidationDecision`` using these rules:

  - any errors        -> HALT (or ROUTE_TO_EXCEPTION, configurable)
  - blocking findings -> ROUTE_TO_EXCEPTION (or QUARANTINE, configurable)
  - warnings only     -> PUBLISH_WITH_WARNINGS
  - none of the above -> PUBLISH

Both ``on_blocking`` and ``on_error`` are validated at construction.
"""
from __future__ import annotations

from typing import Iterable

from ..models.decision import ValidationDecision
from ..models.enums import Severity
from ..models.error import ValidationError
from ..models.finding import ValidationFinding
from ..models.summary import ValidationSummary


_VALID_ON_BLOCKING = {"route_to_exception", "quarantine"}
_VALID_ON_ERROR = {"halt", "route_to_exception"}


class SeverityGateStrategy:
    strategy_id = "severity_gate"

    def __init__(
        self,
        publish_target: str = "publish",
        quarantine_target: str = "quarantine",
        exception_target: str = "exception",
        warnings_target: str | None = None,
        on_blocking: str = "route_to_exception",
        on_error: str = "halt",
    ) -> None:
        if on_blocking not in _VALID_ON_BLOCKING:
            raise ValueError(
                f"on_blocking must be one of {sorted(_VALID_ON_BLOCKING)}, got {on_blocking!r}"
            )
        if on_error not in _VALID_ON_ERROR:
            raise ValueError(
                f"on_error must be one of {sorted(_VALID_ON_ERROR)}, got {on_error!r}"
            )
        self.publish_target = publish_target
        self.quarantine_target = quarantine_target
        self.exception_target = exception_target
        self.warnings_target = warnings_target or publish_target
        self.on_blocking = on_blocking
        self.on_error = on_error

    def decide(
        self,
        findings: Iterable[ValidationFinding],
        errors: Iterable[ValidationError],
        summary: ValidationSummary,  # noqa: ARG002  protocol param; not consulted here
    ) -> ValidationDecision:
        errors = tuple(errors)
        if errors:
            triggered_by = _ordered_unique(e.rule_id or e.error_type for e in errors)
            if self.on_error == "route_to_exception":
                return ValidationDecision.route_to_exception(
                    target=self.exception_target,
                    triggered_by=triggered_by,
                    reason=f"{len(errors)} rule execution error(s)",
                )
            return ValidationDecision.halt(
                target=self.exception_target,
                triggered_by=triggered_by,
                reason=f"{len(errors)} rule execution error(s)",
            )

        findings = tuple(findings)
        blocking = [
            f for f in findings
            if not f.passed and f.severity in (Severity.BLOCKING, Severity.FATAL)
        ]
        if blocking:
            triggered_by = _ordered_unique(f.rule_id for f in blocking)
            if self.on_blocking == "quarantine":
                return ValidationDecision.quarantine(
                    target=self.quarantine_target,
                    triggered_by=triggered_by,
                    reason=f"{len(blocking)} blocking finding(s)",
                )
            return ValidationDecision.route_to_exception(
                target=self.exception_target,
                triggered_by=triggered_by,
                reason=f"{len(blocking)} blocking finding(s)",
            )

        warnings = [
            f for f in findings
            if not f.passed and f.severity == Severity.WARNING
        ]
        if warnings:
            return ValidationDecision.publish_with_warnings(
                target=self.warnings_target,
                triggered_by=_ordered_unique(f.rule_id for f in warnings),
                reason=f"{len(warnings)} warning(s) — publish allowed",
            )

        return ValidationDecision.publish(
            target=self.publish_target,
            reason="No failed findings",
        )


def _ordered_unique(items: Iterable[str]) -> tuple[str, ...]:
    """Preserve first-seen order while de-duplicating (dict preserves insertion order)."""
    return tuple(dict.fromkeys(items))
