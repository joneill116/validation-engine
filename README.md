# Validation Engine

A domain-agnostic validation library for evaluating data payloads against
versioned rule sets, optional imported contract snapshots, thresholds,
and reference data snapshots. It produces deterministic observations,
findings, errors, summaries, outcomes, and audit manifests.

## What it does

- Evaluates configured validation rules against data payloads
- Supports field, entity, collection, group, and relationship targets
- Supports conditional rule applicability (`applies_when`)
- Supports rule dependencies and skipped rules (`depends_on`)
- Produces findings, observations, errors, summaries, outcomes, and manifests
- Supports imported contract and reference-data snapshots
- Remains domain-agnostic and infrastructure-agnostic

## What it does not do

- Does not publish data
- Does not create tickets
- Does not manage contracts
- Does not own reference data
- Does not orchestrate workflows
- Does not write to databases or message buses

## Conceptual flow

```text
ValidationRequest
    -> ValidationEngine
        -> ValidationPlan       (preview without running, optional)
        -> RuleResult           (one per rule executed/skipped)
        -> ValidationFinding    (zero or more per rule)
        -> Observation          (zero or more per rule)
        -> ValidationSummary
        -> ValidationOutcome    (validation-only verdict)
        -> ValidationDecision   (operational interpretation)
        -> ValidationManifest   (audit hashes)
    -> ValidationResult
```

## 60-second example

```python
from validation_engine import (
    ConfigLoader, RulesetCompiler, ValidationEngine, ValidationRequest,
)

cfg = ConfigLoader().load("ruleset.yaml")
compiled = RulesetCompiler().compile(cfg)
engine = ValidationEngine(
    rules=list(compiled.rules),
    strategy=compiled.strategy,
    reference_data=compiled.reference_data,
)

request = ValidationRequest(
    entity_type="record",
    ruleset_id=cfg.ruleset_id,
    payload={"entities": [
        {"entity_ref": {"id": "1"}, "fields": {"x": "value"}},
    ]},
)

result = engine.validate(request)
print(result.outcome.status.value)   # 'passed' / 'passed_with_warnings' / ...
print(result.summary.as_dict())
for f in result.failed_findings():
    print(f.rule_id, f.finding_code, f.message)
```

## Standard rule types

| `rule_type`           | Scope       | Purpose                                            |
| --------------------- | ----------- | -------------------------------------------------- |
| `required`            | entity      | Field key is present                               |
| `not_null`            | field       | Field value is non-null/non-blank                  |
| `enum`                | field       | Value is in an allowed set                         |
| `range`               | field       | Numeric within `[min, max]`                        |
| `regex`               | field       | Matches a regular expression                       |
| `type_check`          | field       | Value is of the declared logical type              |
| `comparison`          | entity      | Compare two fields (`eq`, `gte`, ...)              |
| `date_between`        | field       | Date in inclusive window (or ref window)           |
| `unique`              | collection  | Field/key combination is unique                    |
| `conditional_required`| entity      | Field required when precondition matches           |
| `record_count`        | collection  | Collection size within `[min, max]`                |
| `completeness_ratio`  | collection  | Proportion of populated values meets threshold     |
| `sum_equals`          | collection  | Total of a field equals a target                   |

For anything not covered, write a Python rule (subclass `Rule` or
`ConfiguredRule`) and register it via `RuleFactory.register_class`.

## Authoring custom rules

```python
from validation_engine import (
    EvaluationContext, RuleEvaluation, Severity, Category, Scope,
)
from validation_engine.rules.base import Rule


class MyRule(Rule):
    rule_id = "my.rule"
    scope = Scope.FIELD
    severity = Severity.BLOCKING
    category = Category.BUSINESS_RULE
    field_path = "amount"
    finding_code = "MY_RULE_FAILED"
    applies_to = frozenset({"*"})

    def evaluate(self, ctx: EvaluationContext) -> RuleEvaluation:
        if ctx.field_value is None:
            return self.failed(self.make_finding(
                passed=False, message="amount is required",
            ))
        return self.passed(observations=[
            self.observation("amount", ctx.field_value, unit="raw"),
        ])
```

The legacy `evaluate(self, target, ctx)` form still works — the executor
detects which signature the rule uses.

## Conditional rules and dependencies

```yaml
rules:
  - rule_id: bond.maturity_date.required
    rule_type: not_null
    field_path: maturity_date
    applies_when:
      predicates:
        - field_path: instrument_type
          operator: equals
          value: bond

  - rule_id: bond.maturity_after_issue
    rule_type: comparison
    scope: entity
    depends_on:
      - rule_id: bond.maturity_date.required
    params:
      left: maturity_date
      operator: gte
      right: issue_date
```

A rule whose `applies_when` evaluates false is recorded as
`NOT_APPLICABLE` (distinct from `PASSED`). A rule whose `depends_on`
prerequisites failed is recorded as `SKIPPED`.

## Audit and replay

Every `ValidationResult` includes a `ValidationManifest` carrying
deterministic SHA-256 hashes of the inputs:

```python
result.manifest.payload_hash         # hash of the request payload
result.manifest.ruleset_hash         # hash of the rule set
result.manifest.contract_snapshot_hash  # hash of the contract snapshot, if any
result.manifest.reference_data_hashes   # per-snapshot hashes
result.manifest.engine_version
result.manifest.python_version
```

Same input + same ruleset + same engine version => same hashes.

## Documentation

- [docs/architecture.md](docs/architecture.md)
- [docs/conceptual-model.md](docs/conceptual-model.md)
- [docs/configuration-guide.md](docs/configuration-guide.md)
- [docs/custom-rules.md](docs/custom-rules.md)
- [docs/audit-and-replay.md](docs/audit-and-replay.md)
- [docs/testing.md](docs/testing.md)

Examples:
- [examples/accounting/](examples/accounting/)
- [examples/securities/](examples/securities/)

For the original quick-start guide (publishing-strategy details,
partitioned routing, `ValidationDecision`), see
[QUICKSTART.md](QUICKSTART.md).
