"""
UniqueRule — collection-scope rule asserting a field's values are unique.

Produces one finding per duplicate group plus an aggregate pass finding
if everything is unique.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope
from ...models.finding import ValidationFinding
from ...models import finding_codes
from ..configured import ConfiguredRule
from ._helpers import extract_field


def _ref_id(entity: Any) -> str | None:
    """Extract the most meaningful identifier from an entity_ref, or None."""
    if not isinstance(entity, dict):
        return None
    ref = entity.get("entity_ref")
    if isinstance(ref, dict):
        rid = ref.get("id")
        if rid is not None:
            return str(rid)
    return None


class UniqueRule(ConfiguredRule):
    rule_type = "unique"
    finding_code = finding_codes.DUPLICATE_KEY

    def __init__(self, rule_id: str, **kwargs) -> None:
        kwargs.setdefault("scope", Scope.COLLECTION)
        kwargs.setdefault("category", Category.UNIQUENESS)
        super().__init__(rule_id, **kwargs)
        field_name = self.params.get("field")
        fields_list = self.params.get("fields")
        if not field_name and not fields_list:
            raise ValueError(
                f"UniqueRule {rule_id!r}: 'field' or 'fields' parameter required"
            )
        self.fields: tuple[str, ...] = (
            tuple(fields_list) if fields_list else (field_name,)
        )
        self.ignore_null: bool = bool(self.params.get("ignore_null", True))

    def evaluate(
        self, target: Any, ctx: EvaluationContext
    ) -> Iterable[ValidationFinding]:
        entities = target if isinstance(target, list) else []
        groups: dict[tuple, list[dict]] = defaultdict(list)

        for entity in entities:
            fields = entity.get("fields", {}) if isinstance(entity, dict) else {}
            key_parts = tuple(extract_field(fields, f) for f in self.fields)
            if self.ignore_null and any(v is None or v == "" for v in key_parts):
                continue
            groups[key_parts].append(entity)

        findings: list[ValidationFinding] = []
        for key, members in groups.items():
            if len(members) > 1:
                refs = [r for r in (_ref_id(m) for m in members) if r is not None]
                findings.append(
                    self.make_finding(
                        passed=False,
                        message=self._message(
                            f"Duplicate value for {list(self.fields)}: {key} "
                            f"({len(members)} occurrences)"
                        ),
                        expected="unique",
                        actual={"key": list(key), "occurrences": len(members)},
                        involved_fields=self.fields,
                        evidence={"duplicate_entity_refs": refs},
                    )
                )

        if not findings:
            findings.append(
                self.make_finding(
                    passed=True,
                    message=f"All values for {list(self.fields)} are unique",
                    expected="unique",
                    actual="unique",
                    involved_fields=self.fields,
                )
            )

        return findings
