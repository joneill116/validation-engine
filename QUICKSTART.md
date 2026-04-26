# Quick Start Guide

## Run in 60 Seconds

### 1. Create a rule

```python
from validation_engine import Rule, Severity, Scope, Category, make_finding

class RequiredFieldRule:
    rule_id = "required_field"
    scope = Scope.FIELD
    severity = Severity.BLOCKING
    category = Category.COMPLETENESS
    field_path = "name"
    applies_to = {"*"}
    
    def evaluate(self, target, ctx):
        passed = target is not None and target != ""
        return make_finding(
            self,
            passed=passed,
            message="Field is required" if not passed else "OK",
            field_path=self.field_path,
            actual=target,
        )
```

### 2. Create engine and validate

```python
from validation_engine import ValidationEngine, SeverityGateStrategy

engine = ValidationEngine(
    rules=[RequiredFieldRule()],
    strategy=SeverityGateStrategy(
        publish_target="valid_queue",
        exception_target="invalid_queue",
    ),
)

payload = {
    "entities": [
        {
            "entity_ref": {"id": "1"},
            "fields": {"name": "John"},
        },
    ]
}

decision = engine.validate(
    payload=payload,
    entity_type="record",
    ruleset_id="v1",
)

print(decision.summary)
```

### 3. Done! 🎉

See [example_rules.py](example_rules.py) for complete examples.

## Common Patterns

### Enumeration Check

```python
class StatusRule:
    rule_id = "status_check"
    scope = Scope.FIELD
    severity = Severity.WARNING
    field_path = "status"
    applies_to = {"*"}
    
    def evaluate(self, target, ctx):
        valid = ["active", "inactive", "pending"]
        passed = target in valid
        return make_finding(
            self,
            passed=passed,
            message=f"Invalid status: {target}",
            field_path=self.field_path,
            expected=valid,
            actual=target,
        )
```

### Range Check

```python
class AgeRule:
    rule_id = "age_range"
    scope = Scope.FIELD
    severity = Severity.WARNING
    field_path = "age"
    applies_to = {"*"}
    
    def evaluate(self, target, ctx):
        passed = 0 <= target <= 120
        return make_finding(
            self,
            passed=passed,
            message=f"Age {target} out of range [0-120]",
            field_path=self.field_path,
            actual=target,
        )
```

### Format Check (Regex)

```python
import re

class EmailRule:
    rule_id = "email_format"
    scope = Scope.FIELD
    severity = Severity.BLOCKING
    field_path = "email"
    applies_to = {"*"}
    
    def __init__(self):
        self.pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    
    def evaluate(self, target, ctx):
        passed = bool(self.pattern.match(str(target)))
        return make_finding(
            self,
            passed=passed,
            message=f"Invalid email format: {target}",
            field_path=self.field_path,
            actual=target,
        )
```

### Cross-Field Check (Entity Scope)

```python
class ConsistencyRule:
    rule_id = "start_end_consistency"
    scope = Scope.ENTITY
    severity = Severity.WARNING
    field_path = "*"
    applies_to = {"*"}
    
    def evaluate(self, target, ctx):
        fields = target.get("fields", {})
        start = fields.get("start_date")
        end = fields.get("end_date")
        
        passed = start <= end if (start and end) else True
        return make_finding(
            self,
            passed=passed,
            message="start_date must be before end_date",
            involved_fields=("start_date", "end_date"),
        )
```

### Collection-Level Check

```python
class UniquenessRule:
    rule_id = "unique_id"
    scope = Scope.COLLECTION
    severity = Severity.BLOCKING
    field_path = "*"
    applies_to = {"*"}
    
    def evaluate(self, target, ctx):
        ids = [e["fields"].get("id") for e in target]
        duplicates = [i for i in ids if ids.count(i) > 1]
        
        passed = len(set(duplicates)) == 0
        return make_finding(
            self,
            passed=passed,
            message=f"Duplicate IDs found: {set(duplicates)}",
        )
```

## Advanced Features

### Enable Caching

```python
engine = ValidationEngine(
    rules=rules,
    strategy=strategy,
    enable_cache=True,
    cache_size=50000,  # 50K entries
)

# 50x faster for repeated validations
stats = engine.get_cache_stats()
print(f"Hit rate: {stats['hit_rate_percent']}%")
```

### Add Observability

```python
from validation_engine import ValidationHooks

hooks = ValidationHooks()
hooks.on_validation_start(lambda e: print(f"Started: {e.entity_type}"))
hooks.on_validation_complete(lambda e: print(f"Completed in {e.duration_ms}ms"))
hooks.on_validation_error(lambda e: print(f"Error: {e.error}"))

engine = ValidationEngine(rules=rules, strategy=strategy, hooks=hooks)
```

### Multi-Tenant Setup

```python
from validation_engine import RuleRegistry, StrategyRegistry

# Create registries
rule_registry = RuleRegistry()
rule_registry.register("customer_type", "v1", [Rule1(), Rule2()])
rule_registry.register("order_type", "v1", [Rule3(), Rule4()])

strategy_registry = StrategyRegistry()
strategy_registry.register("standard", SeverityGateStrategy(...))

# Use with engine
engine = ValidationEngine.from_registries(
    rule_registry=rule_registry,
    strategy_registry=strategy_registry,
)

# Validate different entity types
decision1 = engine.validate(payload1, "customer_type", "v1", "standard")
decision2 = engine.validate(payload2, "order_type", "v1", "standard")
```

## Testing

```bash
python3 run_tests.py           # All tests
python3 test_enhancements.py   # Feature tests
python3 showcase_features.py   # Demo
```

## Next Steps

- Read [ARCHITECTURE.md](ARCHITECTURE.md) for complete details
- See [example_rules.py](example_rules.py) for full examples
- Check [TESTING.md](TESTING.md) for testing patterns
