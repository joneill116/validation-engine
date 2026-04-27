# Authoring custom rules

The standard rules cover the common cases. Anything domain-specific
should be a Python class — the validation library doesn't try to be a
DSL.

## Two API shapes

Both work; the executor inspects the class to pick the right call form.

### Context-only (preferred for new code)

```python
from validation_engine import (
    EvaluationContext, RuleEvaluation, Severity, Category, Scope,
)
from validation_engine.rules.base import Rule


class AmountIsPositive(Rule):
    rule_id = "my.amount.positive"
    scope = Scope.FIELD
    severity = Severity.BLOCKING
    category = Category.BUSINESS_RULE
    field_path = "amount"
    finding_code = "AMOUNT_NOT_POSITIVE"
    applies_to = frozenset({"*"})

    def evaluate(self, ctx: EvaluationContext) -> RuleEvaluation:
        v = ctx.field_value
        if v is None:
            return self.not_applicable("amount missing")
        if v <= 0:
            return self.failed(self.make_finding(
                passed=False,
                message=f"amount must be positive, got {v!r}",
                actual=v, expected="> 0",
            ))
        return self.passed(observations=[
            self.observation("amount", v, unit="raw"),
        ])
```

### Legacy positional

```python
class AmountIsPositive(Rule):
    rule_id = "my.amount.positive"
    scope = Scope.FIELD
    severity = Severity.BLOCKING
    category = Category.BUSINESS_RULE
    field_path = "amount"
    applies_to = frozenset({"*"})

    def evaluate(self, target, ctx):
        return self.make_finding(
            passed=isinstance(target, (int, float)) and target > 0,
            message=f"amount {target!r} not positive",
            actual=target,
        )
```

The executor caches the signature on the class and picks the right
form per call.

## What `EvaluationContext` gives you

| Attribute / method            | What it returns                                 |
| ----------------------------- | ----------------------------------------------- |
| `ctx.request`                 | The originating `ValidationRequest`             |
| `ctx.target`                  | The `ValidationTarget` for this evaluation      |
| `ctx.current_entity`          | The current entity dict (entity/field scope)    |
| `ctx.current_field_path`      | Field path under evaluation (field scope)       |
| `ctx.field_value`             | The field value being evaluated (field scope)   |
| `ctx.entity_ref`              | `current_entity["entity_ref"]` shorthand        |
| `ctx.reference_data`          | Engine + request reference data merged          |
| `ctx.get_field("a.b.c")`      | Dotted lookup against `current_entity["fields"]`|
| `ctx.has_field("a.b.c")`      | True iff the path resolves                      |
| `ctx.get_ref("id")`           | Lookup against `entity_ref`                     |
| `ctx.get_reference_data(name)`| Imported reference data by name                 |

## Helper methods on `Rule`

| Method                            | Returns                                       |
| --------------------------------- | --------------------------------------------- |
| `self.passed(observations=())`    | A passing `RuleEvaluation`                    |
| `self.failed(findings, observations=())` | A failing `RuleEvaluation`             |
| `self.not_applicable(reason=None)`| A `NOT_APPLICABLE` `RuleEvaluation`           |
| `self.observation(metric, value, ...)`   | An `Observation` stamped with `rule_id` |
| `self.make_finding(passed, message, ...)`| A `ValidationFinding` with sane defaults |

## Registering for YAML

Once registered, your rule type is reachable from configuration:

```python
from validation_engine import RuleFactory, RulesetCompiler

factory = RuleFactory()
factory.register_class("my.amount.positive", AmountIsPositive)
compiler = RulesetCompiler(rule_factory=factory)
```

```yaml
rules:
  - rule_id: amt.positive
    rule_type: my.amount.positive
    field_path: amount
```

## Rules MUST be deterministic

The same `(target, ctx)` MUST produce the same `(findings, observations,
status)`. This is what makes audit replay possible. Don't read the wall
clock, don't roll dice, don't call external services from inside a
rule. If you need outside data, accept it via reference data and let
the caller hash it into the manifest.

## Standard finding codes

Use the constants in `validation_engine.finding_codes` so dashboards
aggregate consistently:

```python
from validation_engine import finding_codes

self.make_finding(
    ...,
    finding_code=finding_codes.REQUIRED_FIELD_MISSING,
)
```
