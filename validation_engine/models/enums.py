"""
Enumerations used by the validation framework.

Severity / Scope / Category describe individual findings.
ValidationStatus describes the overall run outcome.
RuleExecutionStatus describes how a single rule executed.
DecisionAction describes what downstream systems should do next.
"""
from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    # ERROR sits between WARNING and BLOCKING: it represents a data-quality
    # failure that should not pass silently but isn't necessarily a hard
    # publish blocker on its own. SeverityGateStrategy treats ERROR as
    # publish-blocking by default — same lane as BLOCKING — so existing
    # callers don't accidentally let ERROR-level findings ship.
    ERROR = "error"
    BLOCKING = "blocking"
    FATAL = "fatal"


# Severities that prevent publication. The gate strategy and summary
# aggregation both consult this set so we can extend or override it in one
# place if the policy ever needs to change.
BLOCKING_SEVERITIES: frozenset[Severity] = frozenset(
    {Severity.ERROR, Severity.BLOCKING, Severity.FATAL}
)


class Scope(str, Enum):
    FIELD = "field"
    ENTITY = "entity"
    COLLECTION = "collection"
    # GROUP and RELATIONSHIP are first-class targets for ValidationTarget.
    # The executor only needs them when a rule explicitly opts in via its
    # ``ValidationTarget``; existing FIELD/ENTITY/COLLECTION rules keep the
    # same target-iteration semantics they always had.
    GROUP = "group"
    RELATIONSHIP = "relationship"


class Category(str, Enum):
    STRUCTURAL = "structural"
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    UNIQUENESS = "uniqueness"
    REFERENTIAL = "referential"
    BUSINESS = "business"
    # New categories from the conceptual model (§11.2). Kept as enum members
    # rather than free-form strings so YAML stays validated, but callers can
    # still extend by subclassing if they truly need a custom category.
    TYPE = "type"
    REQUIRED = "required"
    FORMAT = "format"
    RANGE = "range"
    RECONCILIATION = "reconciliation"
    BUSINESS_RULE = "business_rule"
    RUNTIME = "runtime"


class ValidationStatus(str, Enum):
    """Overall outcome of a validation run."""
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    # FAILED is kept for backward-compat (prior callers test on ``FAILED``
    # whenever blocking findings were present). FAILED_BLOCKING is the new
    # explicit name from the conceptual model — both map to the same
    # gate-strategy outcome, so existing tests stay green and new code can
    # opt into the more precise term.
    FAILED = "failed"
    FAILED_BLOCKING = "failed_blocking"
    INVALID_INPUT = "invalid_input"
    ERROR = "error"


class RuleExecutionStatus(str, Enum):
    """How a single rule execution finished."""
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    # NOT_APPLICABLE means the rule's applicability predicate evaluated
    # false for the target. Distinct from SKIPPED (which means a dependency
    # failed or the rule's entity_type didn't match) and from PASSED.
    NOT_APPLICABLE = "not_applicable"


class RuleEvaluationStatus(str, Enum):
    """The status a rule's ``RuleEvaluation`` may report."""
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class DecisionAction(str, Enum):
    """What the platform should do with the validated payload."""
    PUBLISH = "publish"
    PUBLISH_WITH_WARNINGS = "publish_with_warnings"
    QUARANTINE = "quarantine"
    HALT = "halt"
    ROUTE_TO_EXCEPTION = "route_to_exception"
