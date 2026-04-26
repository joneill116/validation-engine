"""
Pytest configuration and shared fixtures.

This file is automatically loaded by pytest and provides reusable fixtures
for all test modules.
"""
import pytest
from test_utils import make_context, make_valid_instrument


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def valid_instrument():
    """Fixture providing a fully valid instrument entity."""
    return make_valid_instrument("fixture_instrument")


@pytest.fixture
def valid_context():
    """Fixture providing a context with a valid instrument."""
    entity = make_valid_instrument("fixture_instrument")
    return make_context(entity)


@pytest.fixture
def us_instrument():
    """Fixture providing a US-based instrument."""
    return make_valid_instrument(
        "us_instrument",
        country_of_risk="US",
        currency="USD",
        isin="US0378331005"
    )


@pytest.fixture
def uk_instrument():
    """Fixture providing a UK-based instrument."""
    return make_valid_instrument(
        "uk_instrument",
        country_of_risk="GB",
        currency="GBP",
        isin="GB0002374006"
    )


@pytest.fixture
def batch_instruments():
    """Fixture providing multiple instruments for batch testing."""
    return [
        make_valid_instrument("inst1", country_of_risk="US"),
        make_valid_instrument("inst2", country_of_risk="GB"),
        make_valid_instrument("inst3", country_of_risk="DE"),
    ]


# ─── Pytest Configuration ─────────────────────────────────────────────────────

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests for individual rules"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests for full validation flows"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take longer to run"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on file location."""
    for item in items:
        # Auto-mark unit tests
        if "test_rules" in str(item.fspath) or "test_examples" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        
        # Auto-mark integration tests
        if "test_end_to_end" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


# ─── Helper Functions ─────────────────────────────────────────────────────────

@pytest.fixture
def rule_test_helper():
    """
    Fixture providing a helper for testing rules.
    
    Usage in tests:
        def test_my_rule(rule_test_helper):
            rule = MyRule()
            finding = rule_test_helper.test_valid(rule, "US")
            assert finding.passed
    """
    class RuleTestHelper:
        def test_valid(self, rule, target, **entity_overrides):
            """Test rule with valid input."""
            entity = make_valid_instrument("test", **entity_overrides)
            ctx = make_context(entity)
            return rule.evaluate(target, ctx)
        
        def test_invalid(self, rule, target, **entity_overrides):
            """Test rule with invalid input."""
            entity = make_valid_instrument("test", **entity_overrides)
            ctx = make_context(entity)
            return rule.evaluate(target, ctx)
    
    return RuleTestHelper()
