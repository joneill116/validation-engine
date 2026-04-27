"""
Core data models for the validation framework.

The central contract:
    ValidationRequest
        -> ValidationEngine
        -> RuleResult
        -> ValidationFinding
        -> ValidationSummary
        -> ValidationDecision
        -> ValidationOutcome
        -> ValidationResult

These models are immutable, audit-friendly, and free of any
domain-specific concepts.
"""
from . import finding_codes
from .decision import ValidationDecision
from .enums import (
    BLOCKING_SEVERITIES,
    Category,
    DecisionAction,
    RuleEvaluationStatus,
    RuleExecutionStatus,
    Scope,
    Severity,
    ValidationStatus,
)
from .error import ValidationError
from .finding import ValidationFinding
from .observation import Observation
from .outcome import ValidationOutcome
from .partition_decision import PartitionDecision
from .request import ValidationRequest
from .result import ValidationResult
from .rule_evaluation import RuleEvaluation
from .rule_result import RuleResult
from .summary import ValidationSummary
from .target import ValidationTarget

__all__ = [
    # enums
    "BLOCKING_SEVERITIES",
    "Severity",
    "Scope",
    "Category",
    "ValidationStatus",
    "RuleExecutionStatus",
    "RuleEvaluationStatus",
    "DecisionAction",
    # core models
    "ValidationRequest",
    "ValidationFinding",
    "RuleResult",
    "RuleEvaluation",
    "ValidationSummary",
    "ValidationDecision",
    "ValidationOutcome",
    "ValidationTarget",
    "Observation",
    "PartitionDecision",
    "ValidationError",
    "ValidationResult",
    # vocab modules
    "finding_codes",
]
