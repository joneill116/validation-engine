from dataclasses import dataclass, field
from typing import Any
from .enums import Severity, Scope, Category


@dataclass(frozen=True)
class Finding:
    rule_id: str
    scope: Scope
    severity: Severity
    category: Category
    passed: bool
    message: str
    field_path: str | None = None
    expected: Any = None
    actual: Any = None
    involved_fields: tuple[str, ...] = field(default_factory=tuple)
    affected_entity_refs: tuple[str, ...] = field(default_factory=tuple)
