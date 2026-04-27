# Changelog

All notable changes to the validation engine.

## [2.1.0] — 2026-04-26

Substantial conceptual-model refactor. All changes are additive — every
2.0.0 import, rule, and test continues to work without modification.

### Added — new vocabulary

- `ValidationOutcome` — validation-only verdict (`PASSED` /
  `PASSED_WITH_WARNINGS` / `FAILED_BLOCKING` / `INVALID_INPUT` /
  `ERROR`). Free of routing language. Lives alongside the existing
  `ValidationDecision` on `ValidationResult.outcome`.
- `ValidationTarget` — first-class object describing what a rule
  evaluates: field / entity / collection / group / relationship.
- `Observation` — measured facts (counts, ratios, totals) emitted by
  rules independent of pass/fail.
- `RuleEvaluation` — structured rule return type with
  `passed` / `failed` / `not_applicable` factories, supporting
  observations and metadata.
- `finding_codes` module — stable machine-readable codes for
  ValidationFinding (`REQUIRED_FIELD_MISSING`, `INVALID_TYPE`,
  `VALUE_OUT_OF_RANGE`, `CONTRACT_FIELD_MISSING`, etc.).
- `ContractSnapshot` + `ContractFieldSnapshot` — immutable inbound
  contract definitions. The engine now synthesizes contract validation
  rules automatically and surfaces violations as findings with
  `CONTRACT_FIELD_MISSING` / `CONTRACT_TYPE_MISMATCH` codes.
- `ReferenceDataSnapshot` — versioned reference data, hashed into the
  manifest, addressable from rules via `ctx.get_reference_data(name)`.
- `ValidationProfile` — declarative run configuration (ruleset
  binding, expected contract identity, required reference data,
  threshold policies). Wired into the engine for pre-flight
  expectation checks.
- `ThresholdPolicy` + `ThresholdBand` — graduated severity bands for
  numeric metrics. `SumEqualsRule` consumes a named policy via the
  request profile, with band severity overriding the rule's static
  severity.
- `RuleApplicability` + `ApplicabilityPredicate` + `PredicateOperator`
  — declarative `applies_when` for conditional rule execution. Rules
  whose predicate evaluates false are recorded as `NOT_APPLICABLE`
  (distinct from `PASSED`).
- `RuleDependency` + `DependencyMode` — declarative `depends_on` for
  rule sequencing. Engine topologically orders rules; compiler rejects
  missing references and cycles.
- `ValidationRuleGroup` (config-only) — author-time grouping of
  rules with cascading severity/category defaults and a stamped
  `group_id` for summary aggregation.
- `ValidationPlan` — preview what `validate(request)` would do
  without executing rules. Available via `engine.plan(request)`.
- `ValidationManifest` — audit/replay receipt with deterministic
  SHA-256 hashes of payload, ruleset, profile, contract snapshot, and
  reference snapshots. Recorded engine version + Python version.
- New standard rules: `type_check` (string/integer/decimal/boolean/
  date/datetime/object/array/any), `record_count` (collection size
  bounds), `completeness_ratio` (proportion of populated values).
- New severity: `Severity.ERROR`, between `WARNING` and `BLOCKING`.
  Treated as publish-blocking by `SeverityGateStrategy`.
- New rule-result status: `RuleExecutionStatus.NOT_APPLICABLE`.
- New `Scope` values: `GROUP`, `RELATIONSHIP`.
- New `Category` values: `TYPE`, `REQUIRED`, `FORMAT`, `RANGE`,
  `RECONCILIATION`, `BUSINESS_RULE`, `RUNTIME`.
- New `ValidationStatus` values: `FAILED_BLOCKING`, `INVALID_INPUT`.

### Added — infrastructure

- `core/hashing.py` — deterministic `stable_hash` (SHA-256 over
  canonical JSON), rejects non-finite floats and non-string mapping
  keys to prevent silent collisions.
- `core/serialization.py` — `to_jsonable` / `from_jsonable` for any
  frozen dataclass; round-trips enums, dataclasses, Decimal,
  datetime, tuple, MappingProxyType, PEP 604 unions.
- `core/paths.py` — dotted-path lookup utilities (`get_path`,
  `path_exists`, `normalize_path`).
- `EvaluationContext` extensions: `target`, `field_value`,
  `entity_ref`, `get_field`, `has_field`, `get_ref`,
  `get_reference_data`, `get_threshold_policy`.
- `Rule` helpers: `self.passed()`, `self.failed(...)`,
  `self.not_applicable(...)`, `self.observation(...)`. Optional
  `self.finding_code` class attribute.
- Engine signature inspection: rules can use either
  `evaluate(self, target, ctx)` (legacy) or `evaluate(self, ctx) ->
  RuleEvaluation` (new). The executor dispatches the right form per
  call.
- Defensive deep-copy of `ValidationRequest.payload` so callers can't
  mutate it after construction.
- Public testing API: `request_builder`, `entity_builder`,
  `ruleset_builder`, `finding_builder`, `assert_passed`,
  `assert_failed`, `assert_has_finding`, `assert_rule_status`,
  `assert_matches_golden`, `write_golden`.

### Added — summary aggregations

`ValidationSummary` now includes failure counts grouped by:

- `by_severity`, `by_category`, `by_rule_id`, `by_finding_code`,
  `by_field_path`, `by_rule_group`.

Plus `not_applicable_count` distinguishing rules whose
`applies_when` predicate evaluated false.

### Added — examples and docs

- `examples/accounting/` and `examples/securities/` — runnable
  end-to-end examples driven by YAML.
- `docs/architecture.md`, `docs/conceptual-model.md`,
  `docs/configuration-guide.md`, `docs/custom-rules.md`,
  `docs/audit-and-replay.md`, `docs/testing.md`.
- New top-level `README.md`. The original `QUICKSTART.md` is
  preserved.

### Fixed

- `finding_id` and `observation_id` now use full 32-char UUID hex
  instead of the truncated 12-char form. Eliminates birthday-collision
  risk for runs aggregating large numbers of findings over time.
- Rule-group default severity/category no longer override values that
  the rule explicitly set. The schema layer distinguishes "user said
  blocking" from "user defaulted to blocking" via `Optional` fields
  resolved to defaults at the factory boundary.
- Outcome computation now reflects pre-flight `ValidationError`s
  (previously only rule-execution errors were counted).

### Internal / runtime

- Rules are topologically ordered by dependency before execution.
- `RuleResult` carries `group_id` and `skip_reason` (when SKIPPED
  due to a dependency).
- `ValidationResult` carries `manifest`, `outcome`, `observations`.
- `ValidationProfile` mismatches (wrong `expected_contract_id`,
  missing required reference data) surface as runtime
  `ValidationError`s, not findings.

### Test surface

273 tests, all green. Coverage: hashing (18), serialization (15),
paths (18), outcome / target / observation / rule-evaluation (25),
rule-API migration + new standard rules (33), applicability /
dependencies / groups / profile model (20), snapshots / threshold /
plan / manifest (15), testing helpers + golden snapshots (12),
production fixes (23), plus the original 93 baseline tests.

### Backward compatibility

- Every 2.0.0 public import still resolves.
- `ValidationDecision` and `SeverityGateStrategy` unchanged.
- Existing rules using `evaluate(self, target, ctx)` returning
  `ValidationFinding` still work — the executor adapts.
- `ValidationStatus.FAILED` retained alongside the new
  `FAILED_BLOCKING` for the same reason.
- Existing YAML rulesets without `applies_when` / `depends_on` /
  `rule_groups` compile and run identically.

## [2.0.0] — initial restructure into core/models/config/registries layout.

## [1.x] — initial release.
