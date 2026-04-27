# Configuration guide

A ruleset is YAML or JSON. Top-level keys:

```yaml
ruleset_id: <string, required>
ruleset_version: <string, default "v1">
entity_type: <string, required>
description: <string, optional>

strategy:
  strategy_type: severity_gate     # or "partitioned"
  params: { ... }

reference_data:                     # optional
  - name: <string>
    inline: <any>                   # or
    path: <relative path to YAML/JSON>

rules:                              # flat list, OR
  - { rule_id, rule_type, ... }

rule_groups:                        # named groups (recommended)
  - group_id: <string>
    default_severity: <severity>
    default_category: <category>
    enabled: true
    rules:
      - { rule_id, rule_type, ... }
```

## Rule keys

| Key            | Type     | Default     | Description                                       |
| -------------- | -------- | ----------- | ------------------------------------------------- |
| `rule_id`      | string   | required    | Stable, unique within the ruleset                  |
| `rule_type`    | string   | required    | One of the standard types or a registered class    |
| `scope`        | enum     | rule default| `field` / `entity` / `collection` / `group` / `relationship` |
| `severity`     | enum     | `blocking`  | `info` / `warning` / `error` / `blocking` / `fatal` |
| `category`     | enum     | `structural`| Functional category (see Severity & Category)      |
| `field_path`   | string   | `*`         | Field this rule targets (FIELD scope)              |
| `applies_to`   | str/list | `*`         | Entity types this rule covers                      |
| `params`       | mapping  | `{}`        | Type-specific parameters                           |
| `enabled`      | bool     | `true`      | When false, the compiler drops the rule            |
| `applies_when` | mapping  | unconditional | Predicate gating (see below)                     |
| `depends_on`   | list     | `[]`        | Prerequisites (see below)                          |
| `group_id`     | string   | optional    | Membership label (auto-set from `rule_groups`)     |

## `applies_when`

Each rule may declare predicates that decide whether it should run:

```yaml
applies_when:
  match: all                       # or "any"; default "all"
  predicates:
    - field_path: instrument_type
      operator: equals
      value: bond
```

Operators: `equals`, `not_equals`, `in`, `not_in`, `exists`,
`not_exists`, `is_null`, `is_not_null`, `greater_than`,
`greater_than_or_equal`, `less_than`, `less_than_or_equal`.

When the predicate evaluates false for a target, the rule is recorded
as `NOT_APPLICABLE` rather than `PASSED`.

## `depends_on`

A rule may depend on another rule's outcome:

```yaml
depends_on:
  - rule_id: bond.maturity_date.required
  - rule_id: bond.coupon_rate.required
    mode: requires_pass            # default; or requires_run / skip_if_failed
```

Or shorthand for a single dependency in `requires_pass` mode:

```yaml
depends_on:
  - bond.maturity_date.required
```

The compiler validates the dependency graph at compile time:
references to unknown rule IDs and cycles are rejected before any data
hits the engine.

## `rule_groups`

Authoring convenience that cascades severity/category defaults across
related rules and lets the summary aggregate by `group_id`:

```yaml
rule_groups:
  - group_id: structural
    default_severity: blocking
    default_category: structural
    rules:
      - rule_id: account_id.required
        rule_type: required
        field_path: account_id
```

The loader flattens groups into the top-level `rules` list, stamping
the `group_id` and applying the group's severity/category as the rule's
defaults. Disabling a group disables every rule in it.

## Strategies

```yaml
strategy:
  strategy_type: severity_gate
  params:
    publish_target: topic.publish
    quarantine_target: topic.quarantine
    exception_target: topic.exception
    warnings_target: topic.publish    # default: same as publish_target
    on_blocking: route_to_exception   # or "quarantine"
    on_error: halt                    # or "route_to_exception"
```

For per-record routing, wrap with `partitioned`:

```yaml
strategy:
  strategy_type: partitioned
  params:
    partition_by: entity_ref.id
    inner:
      strategy_type: severity_gate
      params:
        publish_target: topic.publish
        exception_target: topic.exception
```

`partition_by` accepts:

- `"entity_ref.X"` — partition by an entity_ref key
- `"fields.X"` — partition by a field value
- `"field_path"` — partition by which field had the issue
- `["entity_ref.X", "fields.Y"]` — multi-key tuple
- bare `"X"` — sugar for `entity_ref.X`

## Reference data

```yaml
reference_data:
  - name: iso_currencies
    inline:
      - USD
      - GBP
      - EUR

  - name: account_master
    path: refdata/accounts.json
```

Rules read reference data via `ctx.get_reference_data("iso_currencies")`.

## At runtime: ContractSnapshot and ReferenceDataSnapshot

A request can carry per-run snapshots that get merged with whatever is
configured at engine construction time:

```python
request = ValidationRequest(
    ...,
    contract_snapshot=ContractSnapshot(
        contract_id="acct.position", contract_version="v3",
        entity_type="position",
        fields=(ContractFieldSnapshot("market_value", "decimal", required=True),),
    ),
    reference_data_snapshots={
        "iso_currencies": ReferenceDataSnapshot(
            name="iso_currencies", data=["USD", "GBP"], version="2026-04",
        ),
    },
)
```

Both get hashed into `result.manifest` for replay/audit.
