"""
Testing utilities and fixtures for rule validation tests.

Provides helpers for:
- Creating mock evaluation contexts
- Generating test entities with various field combinations
- Asserting on validation findings
- Parametrized test data generation
"""
from typing import Any, Optional
from validation_engine.engine.context import EvaluationContext
from validation_engine import Severity, make_finding


# ─── Context Creation Helpers ─────────────────────────────────────────────────

def make_context(
    entity: dict,
    entity_type: str = "instrument",
    ruleset_id: str = "test",
    payload: Optional[dict] = None
) -> EvaluationContext:
    """
    Create a minimal EvaluationContext for testing.
    
    Args:
        entity: The entity dict to evaluate
        entity_type: Type identifier (default: "instrument")
        ruleset_id: Ruleset identifier (default: "test")
        payload: Full payload dict (auto-generated if not provided)
    
    Returns:
        EvaluationContext ready for rule evaluation
    
    Example:
        >>> entity = {"instrument_id": "test1", "country_of_risk": "US"}
        >>> ctx = make_context(entity)
        >>> rule.evaluate("US", ctx)
    """
    if payload is None:
        payload = {"entities": [entity]}
    
    return EvaluationContext(
        entity=entity,
        entity_type=entity_type,
        entity_id=entity.get("instrument_id", entity.get("id", "test_entity")),
        ruleset_id=ruleset_id,
        payload=payload,
    )


def make_batch_context(
    entities: list[dict],
    entity_type: str = "instrument",
    ruleset_id: str = "test"
) -> list[EvaluationContext]:
    """
    Create multiple contexts for batch testing.
    
    Args:
        entities: List of entity dicts
        entity_type: Type identifier
        ruleset_id: Ruleset identifier
    
    Returns:
        List of EvaluationContext instances
    
    Example:
        >>> entities = [
        ...     {"instrument_id": "valid", "country_of_risk": "US"},
        ...     {"instrument_id": "invalid", "country_of_risk": "XX"}
        ... ]
        >>> contexts = make_batch_context(entities)
    """
    payload = {"entities": entities}
    return [
        EvaluationContext(
            entity=entity,
            entity_type=entity_type,
            entity_id=entity.get("instrument_id", entity.get("id", f"entity_{i}")),
            ruleset_id=ruleset_id,
            payload=payload,
        )
        for i, entity in enumerate(entities)
    ]


# ─── Entity Generation Helpers ────────────────────────────────────────────────

def make_valid_instrument(
    instrument_id: str = "test_valid",
    **overrides
) -> dict:
    """
    Create a fully valid instrument entity for testing.
    
    All required fields are populated with valid values.
    Use overrides to customize specific fields.
    
    Args:
        instrument_id: Unique identifier
        **overrides: Field overrides
    
    Returns:
        Dict representing a valid instrument
    
    Example:
        >>> instrument = make_valid_instrument("apple", country_of_risk="US")
    """
    base = {
        "instrument_id": instrument_id,
        "isin": "US0378331005",
        "cusip": "037833100",
        "lei": "549300ABCDEFGHIJ1234",
        "issuer_name": "Apple Inc",
        "country_of_risk": "US",
        "currency": "USD",
        "instrument_type": "equity",
        "notional_amount": 1000000,
        "maturity_date": "2030-12-31",
        "credit_rating": "AAA",
    }
    base.update(overrides)
    return base


def make_invalid_instrument(
    instrument_id: str = "test_invalid",
    invalid_fields: Optional[dict] = None
) -> dict:
    """
    Create an instrument with specific invalid fields.
    
    Starts with a valid base and applies invalid field values.
    
    Args:
        instrument_id: Unique identifier
        invalid_fields: Dict of field_name -> invalid_value
    
    Returns:
        Dict representing an invalid instrument
    
    Example:
        >>> instrument = make_invalid_instrument(
        ...     "bad_country",
        ...     invalid_fields={"country_of_risk": "XX"}
        ... )
    """
    base = make_valid_instrument(instrument_id)
    if invalid_fields:
        base.update(invalid_fields)
    return base


def make_minimal_instrument(instrument_id: str = "test_minimal") -> dict:
    """
    Create an instrument with only required fields.
    
    Useful for testing optional field validation.
    
    Args:
        instrument_id: Unique identifier
    
    Returns:
        Dict with minimal fields
    """
    return {
        "instrument_id": instrument_id,
        "isin": "US0378331005",
        "lei": "549300ABCDEFGHIJ1234",
        "issuer_name": "Test Company",
        "country_of_risk": "US",
    }


# ─── Assertion Helpers ────────────────────────────────────────────────────────

def assert_rule_passed(finding, rule_id: Optional[str] = None):
    """
    Assert that a rule evaluation passed.
    
    Args:
        finding: The Finding object from rule.evaluate()
        rule_id: Optional rule_id to verify
    
    Raises:
        AssertionError: If finding did not pass
    
    Example:
        >>> finding = rule.evaluate(target, ctx)
        >>> assert_rule_passed(finding, "country_code")
    """
    assert finding.passed is True, f"Expected rule to pass but got: {finding.message}"
    if rule_id:
        assert finding.rule_id == rule_id, f"Expected rule_id '{rule_id}', got '{finding.rule_id}'"


def assert_rule_failed(finding, rule_id: Optional[str] = None, message_contains: Optional[str] = None):
    """
    Assert that a rule evaluation failed.
    
    Args:
        finding: The Finding object from rule.evaluate()
        rule_id: Optional rule_id to verify
        message_contains: Optional substring expected in failure message
    
    Raises:
        AssertionError: If finding passed or message doesn't match
    
    Example:
        >>> finding = rule.evaluate("XX", ctx)
        >>> assert_rule_failed(finding, message_contains="Invalid country")
    """
    assert finding.passed is False, f"Expected rule to fail but it passed: {finding.message}"
    if rule_id:
        assert finding.rule_id == rule_id, f"Expected rule_id '{rule_id}', got '{finding.rule_id}'"
    if message_contains:
        assert message_contains.lower() in finding.message.lower(), \
            f"Expected message to contain '{message_contains}', got: {finding.message}"


def assert_severity(finding, expected_severity: Severity):
    """
    Assert that a finding has the expected severity level.
    
    Args:
        finding: The Finding object
        expected_severity: Expected Severity enum value
    
    Raises:
        AssertionError: If severity doesn't match
    
    Example:
        >>> assert_severity(finding, Severity.BLOCKING)
    """
    assert finding.severity == expected_severity, \
        f"Expected severity {expected_severity}, got {finding.severity}"


def assert_field_path(finding, expected_path: str):
    """
    Assert that a finding refers to the expected field path.
    
    Args:
        finding: The Finding object
        expected_path: Expected field path string
    
    Raises:
        AssertionError: If field_path doesn't match
    
    Example:
        >>> assert_field_path(finding, "country_of_risk")
    """
    assert finding.field_path == expected_path, \
        f"Expected field_path '{expected_path}', got '{finding.field_path}'"


# ─── Parametrized Test Data Generators ────────────────────────────────────────

def generate_country_test_cases():
    """
    Generate test cases for country code validation.
    
    Returns:
        List of (country_code, should_pass, description) tuples
    
    Example:
        >>> for code, should_pass, desc in generate_country_test_cases():
        ...     # parametrize test with these values
    """
    return [
        ("US", True, "United States"),
        ("GB", True, "United Kingdom"),
        ("DE", True, "Germany"),
        ("XX", False, "Invalid code"),
        ("USA", False, "Three-letter code"),
        ("", False, "Empty string"),
        (None, False, "None value"),
        ("us", False, "Lowercase"),
        ("123", False, "Numeric"),
    ]


def generate_lei_test_cases():
    """
    Generate test cases for LEI validation.
    
    Returns:
        List of (lei, should_pass, description) tuples
    """
    return [
        ("549300ABCDEFGHIJ1234", True, "Valid 20-char LEI"),
        ("123456789012345ABCDE", True, "Valid alphanumeric"),
        ("SHORT", False, "Too short"),
        ("TOOLONGABCDEFGHIJKLMNOP12345", False, "Too long"),
        ("549300ABCDEFGH!J1234", False, "Contains special char"),
        ("", False, "Empty string"),
        (None, False, "None value"),
        ("549300abcdefghij1234", False, "Contains lowercase"),
    ]


def generate_isin_test_cases():
    """
    Generate test cases for ISIN validation.
    
    Returns:
        List of (isin, should_pass, description) tuples
    """
    return [
        ("US0378331005", True, "Valid Apple ISIN"),
        ("GB0002374006", True, "Valid UK ISIN"),
        ("JP3633400001", True, "Valid Japan ISIN"),
        ("INVALID", False, "Too short"),
        ("US037833100", False, "11 characters"),
        ("us0378331005", False, "Lowercase country"),
        ("", False, "Empty string"),
        (None, False, "None value"),
        ("123456789012", False, "Numeric only"),
    ]


def generate_date_test_cases():
    """
    Generate test cases for date validation.
    
    Returns:
        List of (date_string, should_pass, description) tuples
    """
    return [
        ("2030-12-31", True, "Future date"),
        ("2050-01-01", True, "Far future"),
        ("2020-01-01", False, "Past date"),
        ("2010-12-31", False, "Old past date"),
        (None, True, "Optional field"),
        ("", False, "Empty string"),
        ("not-a-date", False, "Invalid format"),
        ("31-12-2030", False, "Wrong format"),
    ]


# ─── Rule Test Pattern ────────────────────────────────────────────────────────

class RuleTestTemplate:
    """
    Base template for testing a single rule with common patterns.
    
    Usage:
        class TestMyRule(RuleTestTemplate):
            def setup_rule(self):
                return MyRule()
            
            def get_valid_cases(self):
                return [("US", {}), ("GB", {})]
            
            def get_invalid_cases(self):
                return [("XX", {}), (None, {})]
    """
    
    def setup_rule(self):
        """Override: Return the rule instance to test."""
        raise NotImplementedError("Implement setup_rule()")
    
    def get_valid_cases(self):
        """Override: Return list of (target, entity_overrides) for valid cases."""
        raise NotImplementedError("Implement get_valid_cases()")
    
    def get_invalid_cases(self):
        """Override: Return list of (target, entity_overrides) for invalid cases."""
        raise NotImplementedError("Implement get_invalid_cases()")
    
    def test_valid_cases(self):
        """Test all valid cases pass."""
        rule = self.setup_rule()
        for target, overrides in self.get_valid_cases():
            entity = make_valid_instrument(**overrides)
            ctx = make_context(entity)
            
            # Field rules evaluate the target directly
            if hasattr(rule, 'field_path') and rule.field_path != "*":
                finding = rule.evaluate(target, ctx)
            else:
                # Entity rules evaluate the whole entity
                finding = rule.evaluate(entity, ctx)
            
            assert_rule_passed(finding, rule.rule_id)
    
    def test_invalid_cases(self):
        """Test all invalid cases fail."""
        rule = self.setup_rule()
        for target, overrides in self.get_invalid_cases():
            entity = make_valid_instrument(**overrides)
            ctx = make_context(entity)
            
            if hasattr(rule, 'field_path') and rule.field_path != "*":
                finding = rule.evaluate(target, ctx)
            else:
                finding = rule.evaluate(entity, ctx)
            
            assert_rule_failed(finding, rule.rule_id)
