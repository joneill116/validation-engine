"""Run the securities-master example end-to-end."""
from __future__ import annotations

from pathlib import Path

from validation_engine import (
    ConfigLoader,
    RulesetCompiler,
    ValidationEngine,
    ValidationRequest,
)


HERE = Path(__file__).parent


def main() -> None:
    cfg = ConfigLoader().load(HERE / "ruleset.yaml")
    compiled = RulesetCompiler(config_dir=HERE).compile(cfg)
    engine = ValidationEngine(
        rules=list(compiled.rules),
        strategy=compiled.strategy,
        reference_data=compiled.reference_data,
    )

    request = ValidationRequest(
        entity_type="security",
        ruleset_id=cfg.ruleset_id,
        ruleset_version=cfg.ruleset_version,
        payload={"entities": [
            {"entity_ref": {"id": "sec-1"}, "fields": {
                "instrument_type": "equity",
                "ccy": "USD",
            }},
            {"entity_ref": {"id": "sec-2"}, "fields": {
                "instrument_type": "bond",
                "ccy": "USD",
                "issue_date": "2020-01-01",
                "maturity_date": "2030-01-01",
                "coupon_rate": "5.00",
            }},
            {"entity_ref": {"id": "sec-3"}, "fields": {
                "instrument_type": "bond",
                "ccy": "GBP",
                # Missing maturity_date and coupon_rate -> bond rules fire.
            }},
        ]},
    )

    plan = engine.plan(request)
    print(f"plan: {len(plan.planned_rules)} rule(s) considered")

    result = engine.validate(request)
    print(f"outcome: {result.outcome.status.value} (valid={result.outcome.is_valid})")
    print(f"summary: {result.summary.as_dict()}")
    for f in result.failed_findings():
        print(f"  - [{f.severity.value}] {f.rule_id} ({f.finding_code}): {f.message}")


if __name__ == "__main__":
    main()
