# Conceptual model

The library is built around a small, stable vocabulary. Every concept
exists to answer one specific question.

| Concept                  | Question it answers                                         |
| ------------------------ | ----------------------------------------------------------- |
| `ValidationRequest`      | What is being validated, by which ruleset, with what inputs?|
| `ValidationProfile`      | What is the complete validation setup for this kind of run? |
| `ContractSnapshot`       | What contract definition was used at validation time?       |
| `ReferenceDataSnapshot`  | What lookup tables were used at validation time?            |
| `ValidationRuleSet`      | Which rules apply to this entity type and ruleset?          |
| `ValidationRuleGroup`    | What logical grouping does each rule belong to?             |
| `ValidationRule`         | What is being checked?                                      |
| `RuleApplicability`      | Should this rule run for this target?                       |
| `RuleDependency`         | Which prerequisite rules must have run/passed first?        |
| `ValidationTarget`       | What is this rule being applied to?                         |
| `EvaluationContext`      | What context does the rule need to make its decision?       |
| `RuleEvaluation`         | What is the rule's structured outcome for this target?      |
| `Observation`            | What did the rule measure?                                  |
| `ValidationFinding`      | What failed (or passed) and why?                            |
| `ValidationError`        | What blew up at runtime?                                    |
| `RuleResult`             | What happened when this rule ran?                           |
| `ValidationSummary`      | What's the headline aggregation across the run?             |
| `ValidationOutcome`      | What's the validation-only verdict?                         |
| `ValidationDecision`     | What should the platform do next? (operational)             |
| `ValidationManifest`     | What inputs produced this result, hashed for replay?        |
| `ValidationPlan`         | What would `validate(request)` do without running it?       |
| `ValidationResult`       | The full audit object containing everything above.          |

## Findings vs Observations vs Errors

Three distinct things, often confused:

- **`ValidationFinding`** — a *data-quality* observation. Pass or fail.
  The rule looked at the data and reported on it.
- **`Observation`** — a *measured fact*. Counts, ratios, totals — the
  numeric raw material a finding may be built from. Emitted regardless
  of pass/fail.
- **`ValidationError`** — a *runtime failure*. The rule code raised an
  exception, or the engine couldn't evaluate the input. Lives on
  `result.errors` and never inside `result.findings`.

A failed business validation is **not** the same as a runtime error.
A NAV that's a penny off is a `Finding`; a `KeyError` inside the rule
is an `Error`.

## NOT_APPLICABLE vs SKIPPED vs PASSED

A rule that doesn't apply to a target is **not** the same as a rule
that passed:

- **`PASSED`** — the rule ran and found no issue.
- **`NOT_APPLICABLE`** — the rule's `applies_when` predicate evaluated
  false. The rule body never ran.
- **`SKIPPED`** — the rule was intentionally skipped, either because
  its `applies_to` didn't match the request's `entity_type`, or because
  one of its `depends_on` prerequisites failed.
- **`FAILED`** — the rule ran and produced one or more failed findings.
- **`ERROR`** — the rule code raised. A `ValidationError` is recorded.

Completeness reporting depends on this distinction: a "we skipped 12
rules because they don't apply" is healthy; a "we passed 12 rules"
when the rules never ran is misleading.

## Outcome vs Decision

Two answers to two different questions:

- **`ValidationOutcome`** — the validation-only verdict
  (`PASSED` / `PASSED_WITH_WARNINGS` / `FAILED_BLOCKING` /
  `INVALID_INPUT` / `ERROR`). Free of routing vocabulary.
  Ask: "is the data valid?"
- **`ValidationDecision`** — the operational interpretation
  (`PUBLISH` / `PUBLISH_WITH_WARNINGS` / `QUARANTINE` /
  `ROUTE_TO_EXCEPTION` / `HALT`). Coupled to the consumer.
  Ask: "what should I do with this data?"

Both live on `ValidationResult`. New code should branch on
`result.outcome.is_valid` for the validation question and
`result.decision.action` only when implementing routing.
