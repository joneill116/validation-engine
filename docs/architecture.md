# Architecture

## Layered structure

The library is organized into five top-level packages. Each layer
depends only on layers below it.

```text
validation_engine/
├── core/         # engine, executor, context, hashing, serialization, paths
├── models/       # immutable input/output dataclasses + enums
├── rules/        # rule abstract base + standard rule implementations
├── strategies/   # publish-decision strategies (severity_gate, partitioned)
├── config/       # YAML/JSON loader, factory, compiler
├── registries/   # rule + strategy lookup tables
└── testing/      # builders, assertions, golden snapshot helpers
```

### models/

Frozen dataclasses with `MappingProxyType` for any mapping field. These
are the sole vocabulary the engine speaks. Nothing here imports from
`core`, `rules`, `strategies`, or `config`.

### core/

The engine, the executor (a per-rule runner), the `EvaluationContext`,
and three pure utilities used everywhere: `hashing` (deterministic
SHA-256 over canonical JSON), `serialization` (`to_jsonable` /
`from_jsonable` for any frozen dataclass), `paths` (dotted-path lookup).

### rules/

The `Rule` abstract base class plus the standard rule implementations.
A rule is a callable that returns a `ValidationFinding`,
`Iterable[ValidationFinding]`, or `RuleEvaluation`. The executor
normalizes whichever shape the rule emits.

### strategies/

`PublishStrategy` and `PerPartitionStrategy` protocols, the default
`SeverityGateStrategy`, and the `PartitionedStrategy` decorator. These
translate run signals (findings, errors, summary) into a
`ValidationDecision`. Note that the validation-only verdict
(`ValidationOutcome`) is computed by the engine itself and does not
depend on a strategy.

### config/

YAML/JSON loader → typed `RulesetConfig` schema → `RulesetCompiler` →
runtime rules + strategy. Authoring conveniences (`rule_groups`,
`applies_when`, `depends_on`) are normalized at this layer.

### registries/

Plain lookup tables: `RuleRegistry` keys by `(entity_type, ruleset_id)`,
`StrategyRegistry` keys by `strategy_id`. Both are optional — the engine
runs equally well from a list of rules and a strategy passed directly.

### testing/

Public testing API: builders for the most common shapes, assertions
that produce informative failure messages, and golden-snapshot helpers
that strip dynamic fields (timestamps, generated IDs) before comparison.

## Execution model

`ValidationEngine.validate(request)` is one method, four steps:

1. **Resolve** — payload shape, rule list, strategy.
2. **Sequence** — topologically order rules so dependencies precede
   dependents.
3. **Execute** — for each rule, iterate its targets (deepcopy each one
   for safety), evaluate, normalize the return value, accumulate
   findings + observations + status.
4. **Assemble** — build `ValidationSummary`, `ValidationDecision`
   (from the strategy), `ValidationOutcome` (from the engine), and a
   `ValidationManifest` with deterministic input hashes.

`engine.plan(request)` runs only step 1 and returns a `ValidationPlan`
describing what step 3 *would* do — useful for previews and for proving
which rules are about to run before paying for the run.

## Determinism guarantees

- Same payload + same ruleset + same engine version => same
  `manifest.payload_hash`, `manifest.ruleset_hash`,
  `manifest.contract_snapshot_hash`, `manifest.reference_data_hashes`.
- Findings within a `RuleResult` keep the order the rule emitted them.
- `ValidationDecision.triggered_by` preserves first-seen order.
- The engine never mutates any input it receives — payload, ruleset,
  contract, and reference snapshots are deep-copied or frozen.

## What lives outside the library

The validation library deliberately stops at producing a result. It
does not own:

- publish/quarantine/exception routing (consume `ValidationOutcome`
  and `ValidationDecision` downstream)
- contract authoring/storage/lifecycle
- reference-data sourcing or governance
- workflow orchestration or messaging

Those concerns belong in adapters built on top of the library.
