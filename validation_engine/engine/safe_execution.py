"""
Safe rule execution with comprehensive error handling.

Wraps rule evaluation to catch and handle errors gracefully,
preventing a single rule failure from breaking the entire validation pipeline.
Provides detailed error diagnostics and structured logging.
"""
import logging
from typing import Any
from ..contracts.findings import Finding
from ..contracts.enums import Severity, Scope, Category
from .context import EvaluationContext

logger = logging.getLogger(__name__)


def safe_evaluate_rule(rule: Any, target: Any, ctx: EvaluationContext) -> Finding:
    """
    Safely evaluate a rule, catching exceptions and converting to findings.
    
    Provides comprehensive error handling for all failure modes:
    - Missing or invalid rule attributes
    - Incorrect evaluate() signatures
    - Runtime exceptions during rule logic
    - Invalid return types
    
    Args:
        rule: The rule instance to evaluate
        target: The target value to validate
        ctx: The evaluation context
        
    Returns:
        Finding object (either from rule or synthesized error finding)
    """
    rule_id = getattr(rule, "rule_id", "unknown_rule")
    
    try:
        # Validate rule has required attributes before execution
        _validate_rule_structure(rule)
        
        # Execute rule
        result = rule.evaluate(target, ctx)
        
        # Validate the result is a Finding
        if not isinstance(result, Finding):
            logger.error(
                f"Rule {rule_id!r} returned invalid type: {type(result).__name__}. "
                f"Expected Finding, got {result!r}"
            )
            return _create_error_finding(
                rule,
                f"Rule returned invalid result type: {type(result).__name__}",
                target,
                ctx
            )
        
        return result
        
    except AttributeError as e:
        # Rule missing required attributes or methods
        logger.error(
            f"Rule {rule_id!r} missing required attributes: {e}",
            exc_info=True
        )
        return _create_error_finding(
            rule,
            f"Rule configuration error: {str(e)}",
            target,
            ctx
        )
        
    except TypeError as e:
        # Wrong parameters passed to evaluate() or method call error
        logger.error(
            f"Rule {rule_id!r} evaluate() signature error: {e}",
            exc_info=True
        )
        return _create_error_finding(
            rule,
            f"Rule evaluation parameter error: {str(e)}",
            target,
            ctx
        )
        
    except ValueError as e:
        # Invalid value encountered during rule logic
        logger.warning(
            f"Rule {rule_id!r} encountered invalid value: {e}"
        )
        return _create_error_finding(
            rule,
            f"Invalid value during validation: {str(e)}",
            target,
            ctx
        )
        
    except Exception as e:
        # Catch-all for unexpected errors
        logger.exception(
            f"Unexpected error in rule {rule_id!r}: {type(e).__name__}: {e}"
        )
        return _create_error_finding(
            rule,
            f"Unexpected error: {type(e).__name__}: {str(e)}",
            target,
            ctx
        )


def _validate_rule_structure(rule: Any) -> None:
    """
    Validate that rule has all required attributes and correct types.
    
    Raises:
        AttributeError: If required attributes are missing
        TypeError: If evaluate is not callable
    """
    required_attrs = ["rule_id", "scope", "severity", "category", "field_path", "applies_to", "evaluate"]
    
    for attr in required_attrs:
        if not hasattr(rule, attr):
            raise AttributeError(f"Rule missing required attribute: {attr!r}")
    
    # Verify evaluate is callable
    if not callable(rule.evaluate):
        raise TypeError(f"Rule.evaluate must be callable, got {type(rule.evaluate).__name__}")


def _create_error_finding(
    rule: Any,
    error_message: str,
    target: Any,
    ctx: EvaluationContext
) -> Finding:
    """
    Create an error Finding when rule execution fails.
    
    Uses FATAL severity to ensure the error is visible and handled appropriately.
    Preserves as much rule metadata as possible while providing clear error context.
    
    Args:
        rule: The rule that failed
        error_message: Description of the error
        target: The target value being validated
        ctx: Evaluation context (currently unused, reserved for future enhancements)
        
    Returns:
        Finding object representing the error
    """
    # Safely extract rule attributes with fallbacks
    rule_id = getattr(rule, "rule_id", "unknown_rule")
    scope = getattr(rule, "scope", Scope.FIELD)
    category = getattr(rule, "category", Category.STRUCTURAL)
    field_path = getattr(rule, "field_path", None)
    
    return Finding(
        rule_id=f"{rule_id}__execution_error",
        scope=scope,
        severity=Severity.FATAL,
        category=category,
        passed=False,
        message=f"Rule execution failed: {error_message}",
        field_path=field_path,
        expected=None,
        actual=repr(target)[:200] if target is not None else None,  # Truncate large values
        involved_fields=(),
        affected_entity_refs=(),
    )
