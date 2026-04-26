"""
ValidationDecision — what the platform should do next.

A decision is one component of a ValidationResult. It expresses an
*action* (publish, quarantine, halt, ...), a target identifier, and
the reason / rule(s) that triggered it. The decision is intentionally
generic: it does not know about Kafka topics, blob storage, or any
other downstream destination.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .enums import DecisionAction


# Maps each DecisionAction to (publish_allowed, quarantine_required, exception_required).
# Keeping this single source of truth prevents the factory methods from drifting.
_ACTION_FLAGS: dict[DecisionAction, tuple[bool, bool, bool]] = {
    DecisionAction.PUBLISH:               (True,  False, False),
    DecisionAction.PUBLISH_WITH_WARNINGS: (True,  False, False),
    DecisionAction.QUARANTINE:            (False, True,  True),
    DecisionAction.ROUTE_TO_EXCEPTION:    (False, False, True),
    DecisionAction.HALT:                  (False, False, True),
}


@dataclass(frozen=True)
class ValidationDecision:
    """
    The platform-level decision derived from a validation run.

    Fields:
        action: What to do (publish, quarantine, halt, ...).
        publish_allowed: True if the payload may be published downstream.
        quarantine_required: True if the payload should be quarantined.
        exception_required: True if a human/exception flow should be triggered.
        target: Logical target identifier (queue name, topic, exception bucket).
        reason: Human-readable rationale.
        triggered_by: Rule ids responsible for the decision.

    Construct via the factory methods (``publish``, ``quarantine``, ...) so
    the boolean flags stay in lockstep with ``action``.
    """

    action: DecisionAction
    publish_allowed: bool
    quarantine_required: bool
    exception_required: bool
    target: str | None = None
    reason: str = ""
    triggered_by: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.triggered_by, tuple):
            object.__setattr__(self, "triggered_by", tuple(self.triggered_by))

    # -- factory methods -------------------------------------------------

    @classmethod
    def for_action(
        cls,
        action: DecisionAction,
        *,
        target: str | None = None,
        reason: str = "",
        triggered_by: tuple[str, ...] = (),
    ) -> "ValidationDecision":
        """Build a decision with action-derived booleans."""
        publish, quarantine, exception = _ACTION_FLAGS[action]
        return cls(
            action=action,
            publish_allowed=publish,
            quarantine_required=quarantine,
            exception_required=exception,
            target=target,
            reason=reason,
            triggered_by=triggered_by,
        )

    @classmethod
    def publish(
        cls, target: str | None = None, reason: str = "No failed findings",
    ) -> "ValidationDecision":
        return cls.for_action(DecisionAction.PUBLISH, target=target, reason=reason)

    @classmethod
    def publish_with_warnings(
        cls,
        target: str | None = None,
        triggered_by: tuple[str, ...] = (),
        reason: str = "Warnings present, publish allowed",
    ) -> "ValidationDecision":
        return cls.for_action(
            DecisionAction.PUBLISH_WITH_WARNINGS,
            target=target, reason=reason, triggered_by=triggered_by,
        )

    @classmethod
    def quarantine(
        cls,
        target: str | None = None,
        triggered_by: tuple[str, ...] = (),
        reason: str = "Blocking findings — quarantined",
    ) -> "ValidationDecision":
        return cls.for_action(
            DecisionAction.QUARANTINE,
            target=target, reason=reason, triggered_by=triggered_by,
        )

    @classmethod
    def route_to_exception(
        cls,
        target: str | None = None,
        triggered_by: tuple[str, ...] = (),
        reason: str = "Routed to exception handler",
    ) -> "ValidationDecision":
        return cls.for_action(
            DecisionAction.ROUTE_TO_EXCEPTION,
            target=target, reason=reason, triggered_by=triggered_by,
        )

    @classmethod
    def halt(
        cls,
        target: str | None = None,
        triggered_by: tuple[str, ...] = (),
        reason: str = "Rule execution error — halt",
    ) -> "ValidationDecision":
        return cls.for_action(
            DecisionAction.HALT,
            target=target, reason=reason, triggered_by=triggered_by,
        )
