# Quick Start

The validation engine turns a `ValidationRequest` into a
`ValidationResult` carrying findings, rule results, summary, and a
platform decision (publish, quarantine, route to exception, halt, ...).

```text
ValidationRequest
    -> ValidationEngine
    -> RuleResult
    -> ValidationFinding
    -> ValidationSummary
    -> ValidationDecision
    -> ValidationResult
```

The framework is **fully domain-agnostic**: entity types, field names,
rule ids, partition keys, ruleset ids and decision targets are all
opaque strings supplied by the caller. The framework attaches no
meaning to any of them. Domain-specific rules are written by
*consumers* of the framework, not packaged inside it.

## Preferred API — config-driven

Define rules in YAML, compile them, send a `ValidationRequest`.

```python
from validation_engine import (
    RulesetCompiler,
    ValidationEngine,
    ValidationRequest,
    load_ruleset,
)

ruleset_config = load_ruleset("path/to/your/ruleset.yaml")
compiled = RulesetCompiler().compile(ruleset_config)

engine = ValidationEngine(
    rules=list(compiled.rules),
    strategy=compiled.strategy,
    reference_data=compiled.reference_data,
)

request = ValidationRequest(
    request_id="REQ-001",
    tenant_id="<your_tenant>",
    data_product_id="<your_data_product>",
    data_flow_id="<your_data_flow>",
    entity_type="<your_entity_type>",
    ruleset_id="<your_ruleset_id>",
    ruleset_version="v1",
    payload={"entities": [
        {"entity_ref": {"id": "1"}, "fields": {"some_field": "value"}},
        # ...
    ]},
)

result = engine.validate(request)

print(result.status.value)            # 'passed' / 'passed_with_warnings' / 'failed' / 'error'
print(result.summary.as_dict())       # {'total_findings': ..., 'pass_rate': ...}
print(result.decision.action.value)   # 'publish' / 'quarantine' / 'route_to_exception' / ...

for finding in result.failed_findings():
    print(finding.rule_id, finding.message, dict(finding.entity_ref))
```

(`ValidationStatus` and `DecisionAction` are `str` enums, so direct
comparisons work: `if result.status == "passed": ...`.)

## YAML rule example

```yaml
ruleset_id: <your_ruleset_id>
ruleset_version: v1
entity_type: <your_entity_type>

strategy:
  strategy_type: severity_gate
  params:
    publish_target: topic.publish
    exception_target: topic.exception
    quarantine_target: topic.quarantine

rules:
  - rule_id: <your.rule.required.field_a>
    rule_type: required
    severity: blocking
    field_path: field_a

  - rule_id: <your.rule.enum.field_b>
    rule_type: enum
    severity: blocking
    field_path: field_b
    params:
      values: [VALUE_X, VALUE_Y]

  - rule_id: <your.rule.regex.field_c>
    rule_type: regex
    severity: blocking
    field_path: field_c
    params:
      pattern: "^[A-Z]{3}$"
```

### Standard rule types

| `rule_type`             | Scope       | Purpose                                    |
| ----------------------- | ----------- | ------------------------------------------ |
| `required`              | entity      | Field key is present                       |
| `not_null`              | field       | Field value is non-null/non-blank          |
| `enum`                  | field       | Value is in an allowed set                 |
| `range`                 | field       | Numeric within `[min, max]`                |
| `regex`                 | field       | Matches a regular expression               |
| `comparison`            | entity      | Compare two fields (`eq`, `gte`, ...)      |
| `date_between`          | field       | Date in inclusive window (or ref window)   |
| `unique`                | collection  | Field/key combination is unique            |
| `conditional_required`  | entity      | Field required when precondition matches   |
| `sum_equals`            | collection  | Total of a field equals a target           |

For anything more complex than these standard types, write a Python
rule (subclass `ConfiguredRule` or implement the `Rule` interface) in
your application code and register it with `RuleFactory`.

## Programmatic API (no YAML)

```python
from validation_engine import (
    Rule, Scope, Severity, Category,
    ValidationEngine, ValidationRequest, SeverityGateStrategy,
)


class MyAllowedValuesRule(Rule):
    rule_id = "my.rule.allowed_values"
    scope = Scope.FIELD
    severity = Severity.BLOCKING
    category = Category.STRUCTURAL
    field_path = "some_field"
    applies_to = frozenset({"<your_entity_type>"})

    def evaluate(self, target, ctx):
        ok = target in {"A", "B", "C"}
        return self.make_finding(
            passed=ok,
            message=f"{target!r} not allowed" if not ok else "ok",
            actual=target,
        )


engine = ValidationEngine(
    rules=[MyAllowedValuesRule()],
    strategy=SeverityGateStrategy(
        publish_target="topic.publish",
        exception_target="topic.exception",
    ),
)

result = engine.validate(ValidationRequest(
    entity_type="<your_entity_type>",
    ruleset_id="rs1",
    payload={"entities": [
        {"entity_ref": {"id": "1"}, "fields": {"some_field": "Z"}},
    ]},
))
```

### Plugging in your own rule types

If you need a domain-specific rule, write the class in your application
code and register it once at startup so YAML configs can reference it
by `rule_type`:

```python
from validation_engine import RuleFactory, RulesetCompiler

factory = RuleFactory()
factory.register_class("my_custom_type", MyCustomRule)
compiler = RulesetCompiler(rule_factory=factory)
```

## Per-partition routing

By default the strategy decides for the whole batch — one bad record
sends everything to the exception target. To route each record (or
each value of any key you choose) independently, **wrap the strategy**
with `PartitionedStrategy`:

```python
from validation_engine import PartitionedStrategy, PartitionBy, SeverityGateStrategy

strategy = PartitionedStrategy(
    inner=SeverityGateStrategy(
        publish_target="topic.publish",
        exception_target="topic.exception",
    ),
    # Pick any key from your entity_ref — the framework treats it as opaque.
    partition_by=PartitionBy.entity_ref("<your_group_key>"),
)
```

After validation, `result.partition_decisions` holds one
`PartitionDecision` per partition. Clean partitions publish; partitions
with blocking findings route to exception:

```python
for pd in result.partition_decisions:
    print(pd.dimension, pd.key, pd.action.value, pd.entity_count, pd.failed_count)
```

`result.decision` (run-level) signals "needs attention" if *any*
partition needs it — useful as an orchestration signal.

### Multi-key partitions (tuples)

Combine partitioners to slice across two or more dimensions:

```python
partition_by=PartitionBy.combine(
    PartitionBy.entity_ref("<key_a>"),
    PartitionBy.field("<key_b>"),
)
# pd.key would be a 2-tuple: (<value_of_key_a>, <value_of_key_b>)
```

### Built-in partitioners

| Helper | Key derived from |
| --- | --- |
| `PartitionBy.entity_ref(name)` | `entity.entity_ref[name]` |
| `PartitionBy.field(name)` | `entity.fields[name]` (supports the `{value: …}` rich shape) |
| `PartitionBy.field_path()` | the field path that produced the finding |
| `PartitionBy.combine(p1, p2, ...)` | concatenated tuple of keys (multi-dimensional) |
| `PartitionBy.custom(fn)` | whatever your callable returns |

The framework attaches no meaning to the key names you choose. Whether
the key is a row id, a tenant id, a category code, a hash bucket, or
anything else is the caller's call.

### YAML form

```yaml
strategy:
  strategy_type: partitioned
  params:
    # Any of these forms work; the framework just reads the key value.
    partition_by: entity_ref.<your_key>           # single key
    # partition_by: [entity_ref.<key_a>, fields.<key_b>]   # multi-key tuple
    inner:
      strategy_type: severity_gate
      params:
        publish_target: topic.publish
        exception_target: topic.exception
```

Semantics worth knowing:

- **Clean entities are included** — entities that produced zero findings appear in `partition_decisions` with a publish action. Iterate the list to route every record.
- **Collection-scope findings** affect the run-level decision but are *not* attached to any specific partition.
- **Run-level rollup is worst-wins** — if any partition needs intervention, `result.decision.action` reflects that.

## Decisions

`ValidationDecision.action` is one of:

- `PUBLISH` — clean, publish-allowed.
- `PUBLISH_WITH_WARNINGS` — only warning-severity findings.
- `QUARANTINE` — blocking findings, hold for review.
- `ROUTE_TO_EXCEPTION` — blocking findings, hand off to an exception flow.
- `HALT` — rule execution error; pipeline stop.

Each decision exposes booleans (`publish_allowed`, `quarantine_required`,
`exception_required`) so downstream code can branch without inspecting
the action enum directly.

## Findings vs Errors

- **`ValidationFinding`** — *data* quality observation (pass or fail).
- **`ValidationError`** — *runtime* / *framework* failure: an
  exception inside a rule, a configuration error, etc. Errors live on
  `result.errors`. They never appear inside `result.findings`.

Run-level `ValidationStatus`:

- `passed` / `passed_with_warnings` — `result.decision.publish_allowed == True`
- `failed` — at least one blocking finding
- `error` — at least one execution error
