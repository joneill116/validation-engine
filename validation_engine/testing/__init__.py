"""
Testing helpers for the validation engine.

Two layers:
  - ``fakes`` (legacy): bare-bones rule classes for the engine's own tests.
  - ``builders`` / ``assertions`` / ``golden``: the public testing API
    that downstream consumers can import to test their own rules.
"""
from .assertions import (
    assert_failed,
    assert_has_finding,
    assert_passed,
    assert_rule_status,
)
from .builders import (
    entity_builder,
    finding_builder,
    request_builder,
    ruleset_builder,
)
from .fakes import entity_rule, field_rule
from .golden import assert_matches_golden, write_golden

__all__ = [
    # builders
    "request_builder",
    "entity_builder",
    "ruleset_builder",
    "finding_builder",
    # assertions
    "assert_passed",
    "assert_failed",
    "assert_has_finding",
    "assert_rule_status",
    # golden tests
    "assert_matches_golden",
    "write_golden",
    # legacy fakes (used by engine's own tests)
    "field_rule",
    "entity_rule",
]
