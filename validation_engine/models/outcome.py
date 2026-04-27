"""
ValidationOutcome — the validation-only verdict, free of routing concerns.

``ValidationDecision`` answers "what should the platform do next?"
(publish, quarantine, route to exception, halt). That's an operational
interpretation of the result, useful but coupled to the consumer.

``ValidationOutcome`` is the *validation* verdict: did the data pass,
warn, fail, hit invalid input, or blow up at runtime? It carries booleans
that downstream code can branch on without knowing about queue topics or
ticketing systems, plus a rationale list explaining why.

``ValidationResult`` exposes both: ``outcome`` is the new core concept,
``decision`` stays for callers that want the routing translation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping

from ._immutable import freeze
from .enums import ValidationStatus


@dataclass(frozen=True)
class ValidationOutcome:
    """
    The validation-only verdict for a run.

    Fields:
        status: The headline status (PASSED / PASSED_WITH_WARNINGS /
            FAILED_BLOCKING / INVALID_INPUT / ERROR).
        is_valid: True iff the data is considered valid (PASSED or
            PASSED_WITH_WARNINGS — anything else means "do not trust").
        has_warnings: True iff at least one warning-severity finding fired.
        has_blocking_findings: True iff at least one blocking-severity
            (BLOCKING / FATAL / ERROR) finding fired.
        has_errors: True iff at least one ``ValidationError`` was raised
            during the run (rule code blew up, etc.).
        rationale: Ordered tuple of short strings explaining the verdict.
        metadata: Free-form context.

    Use ``ValidationOutcome.from_signals(...)`` to build a consistent
    instance from raw counts; the constructor is permissive so existing
    callers and tests can build mocked outcomes by hand.
    """

    status: ValidationStatus
    is_valid: bool
    has_warnings: bool = False
    has_blocking_findings: bool = False
    has_errors: bool = False
    rationale: tuple[str, ...] = field(default_factory=tuple)
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.rationale, tuple):
            object.__setattr__(self, "rationale", tuple(self.rationale))
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))

    # -- factories ------------------------------------------------------

    @classmethod
    def from_signals(
        cls,
        *,
        warning_count: int,
        blocking_count: int,
        error_count: int,
        invalid_input: bool = False,
        rationale: Iterable[str] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> "ValidationOutcome":
        """
        Derive an outcome from aggregate signals.

        Precedence (worst-wins):
          1. invalid_input (input shape couldn't be validated)
          2. error_count > 0 (rule code raised)
          3. blocking_count > 0 (blocking finding present)
          4. warning_count > 0 (warning-only)
          5. otherwise PASSED
        """
        if invalid_input:
            return cls(
                status=ValidationStatus.INVALID_INPUT,
                is_valid=False,
                has_warnings=warning_count > 0,
                has_blocking_findings=blocking_count > 0,
                has_errors=error_count > 0,
                rationale=tuple(rationale) or ("input payload failed validation",),
                metadata=metadata or {},
            )
        if error_count > 0:
            return cls(
                status=ValidationStatus.ERROR,
                is_valid=False,
                has_warnings=warning_count > 0,
                has_blocking_findings=blocking_count > 0,
                has_errors=True,
                rationale=tuple(rationale) or (f"{error_count} rule execution error(s)",),
                metadata=metadata or {},
            )
        if blocking_count > 0:
            return cls(
                status=ValidationStatus.FAILED_BLOCKING,
                is_valid=False,
                has_warnings=warning_count > 0,
                has_blocking_findings=True,
                has_errors=False,
                rationale=tuple(rationale) or (f"{blocking_count} blocking finding(s)",),
                metadata=metadata or {},
            )
        if warning_count > 0:
            return cls(
                status=ValidationStatus.PASSED_WITH_WARNINGS,
                is_valid=True,
                has_warnings=True,
                has_blocking_findings=False,
                has_errors=False,
                rationale=tuple(rationale) or (f"{warning_count} warning(s) — publish allowed",),
                metadata=metadata or {},
            )
        return cls(
            status=ValidationStatus.PASSED,
            is_valid=True,
            rationale=tuple(rationale) or ("no failed findings",),
            metadata=metadata or {},
        )
