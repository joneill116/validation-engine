"""
Run the accounting-position example end-to-end.

This script is intentionally tiny: load YAML, build engine, validate one
batch, print summary + outcome + manifest hashes. It's a working
template, not a framework — copy and adapt.
"""
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
        entity_type="accounting_position",
        ruleset_id=cfg.ruleset_id,
        ruleset_version=cfg.ruleset_version,
        payload={"entities": [
            {"entity_ref": {"id": "p1"}, "fields": {
                "account_id": "ACC-001",
                "market_value": "400000.00",
                "currency": "USD",
            }},
            {"entity_ref": {"id": "p2"}, "fields": {
                "account_id": "ACC-002",
                "market_value": "600000.00",
                "currency": "USD",
            }},
        ]},
    )

    result = engine.validate(request)

    print(f"outcome:  {result.outcome.status.value}  (valid={result.outcome.is_valid})")
    print(f"decision: {result.decision.action.value}  -> {result.decision.target}")
    print(f"summary:  {result.summary.as_dict()}")
    if result.manifest:
        print(f"payload_hash:  {result.manifest.payload_hash}")
        print(f"ruleset_hash:  {result.manifest.ruleset_hash}")
    for f in result.failed_findings():
        print(f"  - [{f.severity.value}] {f.rule_id} ({f.finding_code}): {f.message}")


if __name__ == "__main__":
    main()
