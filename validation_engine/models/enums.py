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
    BLOCKING = "blocking"
    FATAL = "fatal"


class Scope(str, Enum):
    FIELD = "field"
    ENTITY = "entity"
    COLLECTION = "collection"


class Category(str, Enum):
    STRUCTURAL = "structural"
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    UNIQUENESS = "uniqueness"
    REFERENTIAL = "referential"
    BUSINESS = "business"


class ValidationStatus(str, Enum):
    """Overall outcome of a validation run."""
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    FAILED = "failed"
    ERROR = "error"


class RuleExecutionStatus(str, Enum):
    """How a single rule execution finished."""
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class DecisionAction(str, Enum):
    """What the platform should do with the validated payload."""
    PUBLISH = "publish"
    PUBLISH_WITH_WARNINGS = "publish_with_warnings"
    QUARANTINE = "quarantine"
    HALT = "halt"
    ROUTE_TO_EXCEPTION = "route_to_exception"
