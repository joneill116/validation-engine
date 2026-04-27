# Audit and replay

Every `ValidationResult` is a self-contained audit object. It carries
the result, the metrics, the verdicts, and a `ValidationManifest` with
deterministic hashes proving what produced it.

## What's hashed

`stable_hash(value)` is SHA-256 over a canonical JSON form (sorted
keys, normalized `Decimal` / `datetime` / `Enum`, tagged sets so they
don't collide with lists). The engine builds these hashes:

| Field on manifest                    | Hashed input                                |
| ------------------------------------ | ------------------------------------------- |
| `payload_hash`                       | `request.payload`                           |
| `ruleset_hash`                       | The resolved rule list (id, version, scope, severity, category, field_path, applies_to, group_id, depends_on) |
| `contract_snapshot_hash`             | `request.contract_snapshot` (uses snapshot's own hash if provided) |
| `reference_data_hashes[name]`        | Each `ReferenceDataSnapshot` (uses snapshot's own hash if provided) |

Plus identity / runtime fields:

| Field                    | Source                          |
| ------------------------ | ------------------------------- |
| `engine_version`         | `validation_engine.__version__` |
| `python_version`         | `platform.python_version()`     |
| `started_at`             | UTC timestamp at run start      |
| `completed_at`           | UTC timestamp at run completion |

## Replay guarantee

Same payload + same ruleset + same engine version => same hashes.

This holds even when:

- Dict key order differs between runs.
- The payload was constructed from `MappingProxyType` vs a plain dict.
- A `Decimal` was constructed from a string vs an int.
- A `datetime` was timezone-aware vs naive (the ISO form is canonical).

It does **not** hold when:

- Float arithmetic drifts a metric value (always use `Decimal` for
  financial inputs).
- A reference snapshot's `data` mapping uses non-string keys (the
  hasher rejects these to avoid silent collisions).

## Serialization round-trip

Every public model supports `to_jsonable` / `from_jsonable`:

```python
from validation_engine.core.serialization import to_jsonable, from_jsonable
from validation_engine import ValidationResult

encoded = to_jsonable(result)         # plain dict, JSON-serializable
restored = from_jsonable(ValidationResult, encoded)
```

This is how golden snapshots work: persist a result, scrub the
inherently dynamic fields (timestamps, generated IDs), diff.

## Golden snapshot tests

```python
from validation_engine.testing import assert_matches_golden

def test_my_scenario():
    result = engine.validate(my_request)
    assert_matches_golden(result, "tests/golden/my_scenario.json")
```

First run writes the snapshot and **fails** so the author reviews it.
Subsequent runs compare against the snapshot, ignoring:

- `validation_run_id`, `request_id` (per-run UUIDs)
- `started_at`, `completed_at`, `duration_ms` (timing)
- `manifest.engine_version`, `manifest.python_version` (runtime)
- `finding_id`, `observation_id` (generated UUIDs)

The hashes in `manifest.payload_hash` etc. **are** compared — that's
the audit signal you actually care about.

## Out-of-band hashing

Most callers won't need to call `stable_hash` directly, but it's
available:

```python
from validation_engine.core.hashing import canonical_json, stable_hash

stable_hash({"foo": [1, 2], "bar": Decimal("1.50")})
canonical_json({"foo": [1, 2]})    # the canonical JSON byte stream
```
