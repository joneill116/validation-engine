from dataclasses import dataclass, field
from functools import cached_property
from types import MappingProxyType
from typing import Any
from .enums import Severity, Disposition
from .findings import Finding


@dataclass(frozen=True)
class FieldResult:
    """A single field's resolved value and any failures against it.
    
    Frozen to ensure immutability and prevent mutation of validation results.
    """
    field_path: str
    value: Any
    source_system: str | None = None
    signal_id: str | None = None
    failures: tuple[Finding, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return not self.failures

    @property
    def severity_max(self) -> Severity | None:
        if not self.failures:
            return None
        return max(f.severity for f in self.failures)


@dataclass(frozen=True)
class EntityResult:
    """Validation outcome for a single entity.
    
    Frozen to ensure immutability and prevent mutation of validation results.
    Uses MappingProxyType for entity_ref to enforce deep immutability.
    """
    entity_ref: MappingProxyType        # Entity reference identifiers (e.g., {id, type, ...})
    entity_type: str

    good: tuple[tuple[str, FieldResult], ...] = field(default_factory=tuple)   # ((field_path, FieldResult), ...)
    bad: tuple[tuple[str, FieldResult], ...] = field(default_factory=tuple)    # ((field_path, FieldResult), ...)
    entity_findings: tuple[Finding, ...] = field(default_factory=tuple) # cross-field / entity-scope rules

    @property
    def severity_max(self) -> Severity:
        """Return highest severity across all failures.
        
        Returns INFO if no failures exist, representing the baseline "good" state.
        This enables consistent disposition calculation where INFO = PUBLISHABLE.
        """
        candidates: list[Severity] = []
        for field_path, fr in self.bad:
            if fr.severity_max:
                candidates.append(fr.severity_max)
        for f in self.entity_findings:
            if not f.passed:
                candidates.append(f.severity)
        if not candidates:
            # No failures = lowest severity (INFO) = publishable
            return Severity.INFO
        return max(candidates)

    @property
    def disposition(self) -> Disposition:
        sev = self.severity_max
        if sev in (Severity.BLOCKING, Severity.FATAL):
            return Disposition.BLOCKED
        return Disposition.PUBLISHABLE

    def all_failures(self) -> tuple[Finding, ...]:
        """Return all failures across bad fields and entity findings."""
        findings: list[Finding] = []
        for field_path, fr in self.bad:
            findings.extend(fr.failures)
        findings.extend(f for f in self.entity_findings if not f.passed)
        return tuple(findings)

    def warnings(self) -> tuple[Finding, ...]:
        """Return only WARNING severity findings."""
        return tuple(f for f in self.all_failures() if f.severity == Severity.WARNING)


@dataclass(frozen=True)
class CollectionResult:
    """Validation outcome for a batch of entities.
    
    Frozen to ensure summary statistics remain accurate after caching.
    Entities list is immutable via tuple to prevent stale cached summary.
    """
    collection_id: str
    entity_type: str
    ruleset_id: str
    entities: tuple[EntityResult, ...] = field(default_factory=tuple)
    collection_findings: tuple[Finding, ...] = field(default_factory=tuple)

    @cached_property
    def summary(self) -> dict:
        by_disposition: dict[str, int] = {d.value: 0 for d in Disposition}
        by_severity: dict[str, int] = {s.value: 0 for s in Severity}
        rules_evaluated = 0
        rules_failed = 0
        steward_required = 0

        for e in self.entities:
            by_disposition[e.disposition.value] += 1
            by_severity[e.severity_max.value] += 1
            all_f = e.all_failures()
            rules_evaluated += len(e.good) + len(e.bad) + len(e.entity_findings)
            rules_failed += len(all_f)
            if e.disposition == Disposition.BLOCKED:
                steward_required += 1

        collection_passed = all(f.passed for f in self.collection_findings)

        return {
            "entity_count": len(self.entities),
            "by_disposition": by_disposition,
            "by_severity": by_severity,
            "rules_evaluated": rules_evaluated,
            "rules_failed": rules_failed,
            "steward_required_count": steward_required,
            "collection_rules_passed": collection_passed,
        }
