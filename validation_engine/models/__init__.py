"""
Core data models for the validation framework.

The central contract:
    ValidationRequest
        -> ValidationEngine
        -> RuleResult
        -> ValidationFinding
        -> ValidationSummary
        -> ValidationDecision
        -> ValidationResult

These models are immutable, audit-friendly, and free of any
domain-specific concepts.
"""
from .decision import ValidationDecision
from .enums import (
    Category,
    DecisionAction,
    RuleExecutionStatus,
    Scope,
    Severity,
    ValidationStatus,
)
from .error import ValidationError
from .finding import ValidationFinding
from .partition_decision import PartitionDecision
from .request import ValidationRequest
from .result import ValidationResult
from .rule_result import RuleResult
from .summary import ValidationSummary

__all__ = [
    "Severity",
    "Scope",
    "Category",
    "ValidationStatus",
    "RuleExecutionStatus",
    "DecisionAction",
    "ValidationRequest",
    "ValidationFinding",
    "RuleResult",
    "ValidationSummary",
    "ValidationDecision",
    "PartitionDecision",
    "ValidationError",
    "ValidationResult",
]
