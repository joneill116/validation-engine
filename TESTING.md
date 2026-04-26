# Testing Guide for Validation Rules

This guide explains how to test validation rules using the testing framework.

## Quick Start

### Run all tests
```bash
python3 run_tests.py
```

### Run specific test categories
```bash
python3 run_tests.py unit          # Only unit tests
python3 run_tests.py integration   # Only integration tests
python3 run_tests.py test_rules    # Specific test file
python3 run_tests.py -k country    # Tests matching 'country'
```

**Note:** On Linux/macOS, you can also make the script executable:
```bash
chmod +x run_tests.py
./run_tests.py
```

## Testing Utilities

The `test_utils.py` module provides helpers for rule testing:

### Context Creation

```python
from test_utils import make_context

# Simple context
entity = {"instrument_id": "test1", "country_of_risk": "US"}
ctx = make_context(entity)

# Custom entity type
ctx = make_context(entity, entity_type="bond")
```

### Entity Generators

```python
from test_utils import (
    make_valid_instrument,
    make_invalid_instrument,
    make_minimal_instrument
)

# Fully valid instrument
instrument = make_valid_instrument("apple", country_of_risk="US")

# Invalid instrument
instrument = make_invalid_instrument(
    "bad_country",
    invalid_fields={"country_of_risk": "XX"}
)

# Minimal required fields only
instrument = make_minimal_instrument("minimal")
```

### Assertion Helpers

```python
from test_utils import (
    assert_rule_passed,
    assert_rule_failed,
    assert_severity,
    assert_field_path
)

# Assert rule passed
finding = rule.evaluate(target, ctx)
assert_rule_passed(finding, "country_code")

# Assert rule failed with message check
assert_rule_failed(finding, message_contains="Invalid country")

# Assert severity level
assert_severity(finding, Severity.BLOCKING)

# Assert field path
assert_field_path(finding, "country_of_risk")
```

## Testing Patterns

### Pattern 1: Simple Test

```python
import pytest
from test_utils import make_context, make_valid_instrument, assert_rule_passed
from rule_inventory import CountryCodeRule

@pytest.mark.unit
def test_country_code_valid():
    """Test CountryCodeRule with valid country."""
    rule = CountryCodeRule()
    entity = make_valid_instrument("test", country_of_risk="US")
    ctx = make_context(entity)
    
    finding = rule.evaluate("US", ctx)
    
    assert_rule_passed(finding, "country_code")
```

### Pattern 2: Parametrized Tests

```python
@pytest.mark.unit
@pytest.mark.parametrize("country,should_pass", [
    ("US", True),
    ("GB", True),
    ("XX", False),
    (None, False),
])
def test_country_code_parametrized(country, should_pass):
    """Test country code rule with multiple inputs."""
    rule = CountryCodeRule()
    entity = make_valid_instrument("test", country_of_risk=country)
    ctx = make_context(entity)
    
    finding = rule.evaluate(country, ctx)
    
    assert finding.passed == should_pass
```

### Pattern 3: Using Test Case Generators

```python
from test_utils import generate_country_test_cases

@pytest.mark.unit
@pytest.mark.parametrize(
    "country,should_pass,description",
    generate_country_test_cases()
)
def test_country_code_comprehensive(country, should_pass, description):
    """Test country code with pre-generated test cases."""
    rule = CountryCodeRule()
    entity = make_valid_instrument("test", country_of_risk=country)
    ctx = make_context(entity)
    
    finding = rule.evaluate(country, ctx)
    
    assert finding.passed == should_pass, f"Failed: {description}"
```

### Pattern 4: Template-Based Testing

```python
from test_utils import RuleTestTemplate

@pytest.mark.unit
class TestMyRule(RuleTestTemplate):
    """Test MyRule using template pattern."""
    
    def setup_rule(self):
        return MyRule()
    
    def get_valid_cases(self):
        return [
            ("US", {"country_of_risk": "US"}),
            ("GB", {"country_of_risk": "GB"}),
        ]
    
    def get_invalid_cases(self):
        return [
            ("XX", {"country_of_risk": "XX"}),
            (None, {"country_of_risk": None}),
        ]
```

## Test Organization

### File Structure

```
tests/
├── __init__.py
├── test_utils.py           # Testing utilities and helpers
├── test_rules.py           # Unit tests for all rules
├── test_examples.py        # Example tests showing patterns
├── test_end_to_end.py      # Integration tests
└── conftest.py             # Pytest configuration (if needed)
```

### Test Markers

Use markers to categorize tests:

```python
@pytest.mark.unit          # Unit tests for individual rules
@pytest.mark.integration   # Integration tests for full flows
@pytest.mark.slow          # Tests that take longer to run
@pytest.mark.parametrize   # Parametrized tests
```

Run specific markers:
```bash
pytest -m unit             # Only unit tests
pytest -m "not slow"       # Exclude slow tests
```

## Best Practices

### 1. Test Both Success and Failure
Always test both valid and invalid inputs:

```python
def test_rule_valid():
    # Test with valid input
    finding = rule.evaluate(valid_input, ctx)
    assert_rule_passed(finding)

def test_rule_invalid():
    # Test with invalid input
    finding = rule.evaluate(invalid_input, ctx)
    assert_rule_failed(finding)
```

### 2. Test Edge Cases
Include edge cases like empty strings, None, whitespace:

```python
@pytest.mark.parametrize("edge_case", ["", None, " ", "\n"])
def test_rule_edge_cases(edge_case):
    finding = rule.evaluate(edge_case, ctx)
    assert_rule_failed(finding)
```

### 3. Test Error Handling
Verify rules handle malformed input:

```python
def test_rule_handles_errors():
    """Test rule with malformed input."""
    entity = {}  # Missing required fields
    ctx = make_context(entity)
    
    # Should not raise exception
    finding = rule.evaluate(None, ctx)
    assert finding is not None
```

### 4. Use Descriptive Test Names
Test names should clearly indicate what is being tested:

```python
def test_country_code_rule_accepts_valid_us_code()
def test_country_code_rule_rejects_invalid_xx_code()
def test_country_code_rule_rejects_none_value()
```

### 5. Keep Tests Independent
Each test should be self-contained and not depend on other tests:

```python
def test_example():
    # Create fresh rule instance
    rule = MyRule()
    
    # Create fresh entity
    entity = make_valid_instrument("test")
    
    # Test
    finding = rule.evaluate(entity, ctx)
```

## Example Test File

See [test_examples.py](test_examples.py) for complete working examples of all patterns.

## Troubleshooting

### pytest not found
```bash
pip install pytest pyyaml
```

### Module not found
```bash
# Make sure you're in the project root
cd /path/to/validation-engine

# Or set PYTHONPATH
export PYTHONPATH=/path/to/validation-engine:$PYTHONPATH
```

### Tests not discovered
Check that:
- Test files start with `test_`
- Test functions start with `test_`
- Test classes start with `Test`
- Files are in the `tests/` directory

## Advanced Topics

### Custom Fixtures
Create reusable test fixtures in `conftest.py`:

```python
# tests/conftest.py
import pytest

@pytest.fixture
def sample_instrument():
    return make_valid_instrument("fixture_instrument")

# Use in tests
def test_with_fixture(sample_instrument):
    ctx = make_context(sample_instrument)
    # ... test code
```

### Mocking Reference Data
Mock external reference data for testing:

```python
from unittest.mock import patch

def test_with_mocked_reference_data():
    with patch('validation_engine.reference.get_reference_data') as mock:
        mock.return_value = {"valid_countries": ["US", "GB"]}
        # ... test code
```

### Coverage Reports
Install pytest-cov and run:

```bash
pip install pytest-cov
pytest --cov=validation_engine --cov-report=html
```

View report:
```bash
open htmlcov/index.html
```

## Next Steps

1. Review [test_examples.py](test_examples.py) for working examples
2. Run existing tests: `python3 run_tests.py`
3. Write tests for your custom rules using the patterns above
4. Add integration tests in `test_end_to_end.py`
5. Set up continuous integration to run tests automatically
