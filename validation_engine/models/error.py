"""
ValidationError — a framework / runtime execution problem.

Distinct from ValidationFinding which represents *data* quality issues.
ValidationError represents *infrastructure* / *engine* / *rule code*
problems: unexpected exceptions, configuration errors, missing
dependencies, malformed payloads, etc.
"""
from __future__ import annotations

import traceback as _tb
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping

from ._immutable import freeze


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ValidationError:
    """
    A runtime / framework execution failure (NOT a data quality issue).

    Fields:
        error_type: Class name of the exception (e.g. 'KeyError').
        message: Human-readable error description.
        rule_id: Rule whose execution failed (if applicable).
        rule_version: Version of the failing rule.
        traceback: Optional traceback for diagnosis.
        timestamp: When the error occurred (UTC).
        context: Free-form structured context.
    """

    error_type: str
    message: str
    rule_id: str | None = None
    rule_version: str | None = None
    traceback: str | None = None
    timestamp: datetime = field(default_factory=_utc_now)
    context: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.context, MappingProxyType):
            object.__setattr__(self, "context", freeze(self.context))

    @classmethod
    def from_exception(
        cls,
        exc: BaseException,
        rule_id: str | None = None,
        rule_version: str | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> "ValidationError":
        return cls(
            error_type=type(exc).__name__,
            message=str(exc) or repr(exc),
            rule_id=rule_id,
            rule_version=rule_version,
            traceback="".join(_tb.format_exception(type(exc), exc, exc.__traceback__)),
            context=freeze(context),
        )
