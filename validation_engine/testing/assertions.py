"""
Assertions for tests.

Pytest-friendly helpers that produce informative failure messages when a
``ValidationResult`` doesn't match expectations. They raise ``AssertionError``
so they slot into existing test suites with no plugin required.
"""
from __future__ import annotations

from ..models.enums import RuleExecutionStatus, ValidationStatus
from ..models.result import ValidationResult


def assert_passed(result: ValidationResult) -> None:
    """Assert the run completed valid (PASSED or PASSED_WITH_WARNINGS)."""
    if result.outcome is not None:
        if not result.outcome.is_valid:
            raise AssertionError(
                f"expected valid outcome; got {result.outcome.status.value}: "
                f"rationale={list(result.outcome.rationale)!r} "
                f"failed={result.summary.failed_count} errors={result.summary.error_count}"
            )
        return
    # Fallback to legacy ``status`` if outcome wasn't populated.
    if result.status not in (
        ValidationStatus.PASSED, ValidationStatus.PASSED_WITH_WARNINGS,
    ):
        raise AssertionError(f"expected passed status; got {result.status.value}")


def assert_failed(result: ValidationResult) -> None:
    """Assert the run failed (any non-valid status)."""
    if result.outcome is not None and result.outcome.is_valid:
        raise AssertionError(
            f"expected failure; got valid outcome {result.outcome.status.value}"
        )
    if result.outcome is None and result.status in (
        ValidationStatus.PASSED, ValidationStatus.PASSED_WITH_WARNINGS,
    ):
        raise AssertionError(f"expected failure; got {result.status.value}")


def assert_has_finding(
    result: ValidationResult,
    *,
    code: str | None = None,
    rule_id: str | None = None,
    field_path: str | None = None,
) -> None:
    """
    Assert the result contains at least one failed finding matching the criteria.

    All supplied filters are AND-ed. ``None`` filters are ignored.
    """
    matches = []
    for f in result.findings:
        if f.passed:
            continue
        if code is not None and f.finding_code != code:
            continue
        if rule_id is not None and f.rule_id != rule_id:
            continue
        if field_path is not None and f.field_path != field_path:
            continue
        matches.append(f)
    if not matches:
        criteria = {
            k: v for k, v in
            (("code", code), ("rule_id", rule_id), ("field_path", field_path))
            if v is not None
        }
        seen = [
            (f.rule_id, f.finding_code, f.field_path, f.message)
            for f in result.findings if not f.passed
        ]
        raise AssertionError(
            f"no failed finding matched {criteria!r}. failed findings: {seen!r}"
        )


def assert_rule_status(
    result: ValidationResult,
    rule_id: str,
    status: RuleExecutionStatus,
) -> None:
    """Assert the named rule produced ``status`` in this run."""
    matches = [r for r in result.rule_results if r.rule_id == rule_id]
    if not matches:
        all_ids = sorted(r.rule_id for r in result.rule_results)
        raise AssertionError(
            f"rule_id {rule_id!r} not found in result. seen: {all_ids!r}"
        )
    if matches[0].status is not status:
        raise AssertionError(
            f"expected rule {rule_id!r} status {status.value!r}; "
            f"got {matches[0].status.value!r}"
        )
