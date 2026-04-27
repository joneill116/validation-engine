"""
Standard ``finding_code`` constants.

Findings carry a stable ``finding_code`` (machine-readable) alongside
their human-readable ``message``. Codes are SCREAMING_SNAKE_CASE strings
so they aggregate well in dashboards and downstream pipelines.

Codes here are conventions, not a closed set: callers can add their own
domain-specific codes. The standard rules in
``validation_engine.rules.standard`` populate findings with these codes
where applicable.
"""
from __future__ import annotations

# Required / structural
REQUIRED_FIELD_MISSING = "REQUIRED_FIELD_MISSING"
INVALID_TYPE = "INVALID_TYPE"
INVALID_FORMAT = "INVALID_FORMAT"

# Range / membership
VALUE_OUT_OF_RANGE = "VALUE_OUT_OF_RANGE"
VALUE_NOT_ALLOWED = "VALUE_NOT_ALLOWED"

# Uniqueness / referential
DUPLICATE_KEY = "DUPLICATE_KEY"
NON_UNIQUE_VALUE = "NON_UNIQUE_VALUE"
REFERENTIAL_VALUE_NOT_FOUND = "REFERENTIAL_VALUE_NOT_FOUND"

# Completeness / reconciliation
COMPLETENESS_BELOW_THRESHOLD = "COMPLETENESS_BELOW_THRESHOLD"
RECONCILIATION_BREAK = "RECONCILIATION_BREAK"

# Cross-field / business
COMPARISON_FAILED = "COMPARISON_FAILED"
CONDITIONAL_REQUIRED_FIELD_MISSING = "CONDITIONAL_REQUIRED_FIELD_MISSING"

# Contract derived
CONTRACT_FIELD_MISSING = "CONTRACT_FIELD_MISSING"
CONTRACT_TYPE_MISMATCH = "CONTRACT_TYPE_MISMATCH"

# Runtime / engine
RULE_EXECUTION_ERROR = "RULE_EXECUTION_ERROR"


__all__ = [
    "REQUIRED_FIELD_MISSING",
    "INVALID_TYPE",
    "INVALID_FORMAT",
    "VALUE_OUT_OF_RANGE",
    "VALUE_NOT_ALLOWED",
    "DUPLICATE_KEY",
    "NON_UNIQUE_VALUE",
    "REFERENTIAL_VALUE_NOT_FOUND",
    "COMPLETENESS_BELOW_THRESHOLD",
    "RECONCILIATION_BREAK",
    "COMPARISON_FAILED",
    "CONDITIONAL_REQUIRED_FIELD_MISSING",
    "CONTRACT_FIELD_MISSING",
    "CONTRACT_TYPE_MISMATCH",
    "RULE_EXECUTION_ERROR",
]
