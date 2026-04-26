from typing import Any, Protocol, runtime_checkable
from ..contracts.enums import Severity, Scope, Category
from ..contracts.findings import Finding
from ..engine.context import EvaluationContext


@runtime_checkable
class Rule(Protocol):
    """
    Protocol every rule must satisfy.

    - field_path: only used by FIELD-scope rules.
      Set to the specific field name (e.g. "country_of_risk") or "*" to run
      against every field.
    - applies_to: set of entity_type strings this rule covers, or {"*"} for all.
    """
    rule_id: str
    scope: Scope
    severity: Severity
    category: Category
    field_path: str          # required; ignored for ENTITY/COLLECTION scope rules
    applies_to: set[str]

    def evaluate(self, target: Any, ctx: EvaluationContext) -> Finding: ...


def make_finding(
    rule: Rule,
    passed: bool,
    message: str,
    field_path: str | None = None,
    expected: Any = None,
    actual: Any = None,
    involved_fields: tuple[str, ...] = (),
    affected_entity_refs: tuple[str, ...] = (),
) -> Finding:
    """Convenience constructor so rule authors don't repeat boilerplate."""
    return Finding(
        rule_id=rule.rule_id,
        scope=rule.scope,
        severity=rule.severity,
        category=rule.category,
        passed=passed,
        message=message,
        field_path=field_path,
        expected=expected,
        actual=actual,
        involved_fields=involved_fields,
        affected_entity_refs=affected_entity_refs,
    )
