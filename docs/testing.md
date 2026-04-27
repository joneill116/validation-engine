# Testing

The validation engine ships its own testing helpers under
`validation_engine.testing`. Use them in downstream test suites; the
engine's own tests use the same helpers.

## Builders

```python
from validation_engine.testing import (
    request_builder, entity_builder, ruleset_builder, finding_builder,
)
from validation_engine import RuleConfig

req = request_builder(entities=[
    entity_builder(entity_id="1", fields={"x": "v"}),
    entity_builder(entity_id="2", fields={"x": None}),
])

ruleset = ruleset_builder(rules=[
    RuleConfig(rule_id="r.required", rule_type="required", field_path="x"),
])
```

## Assertions

```python
from validation_engine.testing import (
    assert_passed, assert_failed, assert_has_finding, assert_rule_status,
)
from validation_engine import RuleExecutionStatus, finding_codes

assert_passed(result)
assert_failed(result)
assert_has_finding(result, code=finding_codes.REQUIRED_FIELD_MISSING)
assert_has_finding(result, rule_id="r.required", field_path="x")
assert_rule_status(result, "r.required", RuleExecutionStatus.PASSED)
```

Each assertion produces an informative failure message naming exactly
which expectation didn't match.

## Golden snapshots

```python
from validation_engine.testing import assert_matches_golden

def test_clean_run():
    result = engine.validate(my_request)
    assert_matches_golden(result, "tests/golden/clean.json")
```

See [audit-and-replay.md](audit-and-replay.md#golden-snapshot-tests) for
the dynamic-field handling.

## Tips

- Test rule logic in isolation by calling `rule.evaluate(...)` directly
  with a hand-built `EvaluationContext`. The engine isn't required.
- For end-to-end tests, the YAML in `examples/` is a working template —
  copy it into `tests/fixtures/` and tweak.
- When a behavioural change is intentional, refresh golden snapshots
  with `write_golden(result, path)` rather than editing the JSON by
  hand.
