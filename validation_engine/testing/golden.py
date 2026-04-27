"""
Golden-result testing helpers.

A "golden" snapshot is a JSON file produced from a known-good
``ValidationResult``. ``assert_matches_golden`` compares a freshly
produced result against its stored snapshot, ignoring fields that
*always* vary between runs (timestamps, generated IDs, durations, hash
of the python interpreter version).

Use ``write_golden`` to refresh a snapshot when the underlying behaviour
intentionally changes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.serialization import to_jsonable
from ..models.result import ValidationResult


# Top-level keys that vary per run.
_DEFAULT_IGNORE_PATHS: tuple[str, ...] = (
    "validation_run_id",
    "request_id",
    "started_at",
    "completed_at",
    "duration_ms",
    "manifest.validation_run_id",
    "manifest.request_id",
    "manifest.started_at",
    "manifest.completed_at",
    "manifest.python_version",
    "manifest.engine_version",
)


# Field names that are *always* dynamic wherever they appear in the tree.
# Stripped recursively from every nested mapping. Matches generated IDs
# (finding_id, observation_id) and per-rule timing.
_DYNAMIC_KEYS: frozenset[str] = frozenset({
    "finding_id",
    "observation_id",
    "observation_ids",
    "duration_ms",
})


def assert_matches_golden(
    result: ValidationResult,
    golden_path: str | Path,
    *,
    ignore: tuple[str, ...] = _DEFAULT_IGNORE_PATHS,
    update: bool = False,
) -> None:
    """
    Compare ``result`` to the JSON snapshot at ``golden_path``.

    When ``update=True`` the snapshot is rewritten from the current
    result instead of being compared. That's useful for the rare cases
    where a behavioural change is intentional and the snapshot must be
    regenerated.
    """
    path = Path(golden_path)
    actual = _scrub(to_jsonable(result), ignore)

    if update or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(actual, indent=2, sort_keys=True), encoding="utf-8")
        if not update:
            # First-time write should fail loudly so the author notices
            # and reviews the snapshot before committing it.
            raise AssertionError(
                f"golden file did not exist; wrote initial snapshot to {path}"
            )
        return

    expected = _scrub(json.loads(path.read_text(encoding="utf-8")), ignore)
    if actual != expected:
        # Compute a small diff hint for the message.
        raise AssertionError(_format_diff(expected, actual, str(path)))


def write_golden(result: ValidationResult, golden_path: str | Path) -> None:
    """Force-write the golden snapshot. Use only when the change is intentional."""
    Path(golden_path).parent.mkdir(parents=True, exist_ok=True)
    Path(golden_path).write_text(
        json.dumps(_scrub(to_jsonable(result), _DEFAULT_IGNORE_PATHS), indent=2, sort_keys=True),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------

def _scrub(value: Any, paths: tuple[str, ...]) -> Any:
    for path in paths:
        _delete_path(value, path.split("."))
    _scrub_dynamic_keys(value)
    return value


def _delete_path(value: Any, parts: list[str]) -> None:
    if not isinstance(value, dict) or not parts:
        return
    head, *tail = parts
    if not tail:
        value.pop(head, None)
        return
    nested = value.get(head)
    if isinstance(nested, dict):
        _delete_path(nested, tail)


def _scrub_dynamic_keys(value: Any) -> None:
    """Recursively delete every appearance of the dynamic-key set."""
    if isinstance(value, dict):
        for key in list(value.keys()):
            if key in _DYNAMIC_KEYS:
                del value[key]
            else:
                _scrub_dynamic_keys(value[key])
    elif isinstance(value, list):
        for item in value:
            _scrub_dynamic_keys(item)


def _format_diff(expected: Any, actual: Any, path: str) -> str:
    expected_text = json.dumps(expected, indent=2, sort_keys=True)
    actual_text = json.dumps(actual, indent=2, sort_keys=True)
    return (
        f"golden snapshot mismatch at {path}\n"
        f"--- expected ---\n{expected_text}\n"
        f"--- actual ---\n{actual_text}"
    )
