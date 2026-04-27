"""
Dotted path utilities for navigating nested entity payloads.

Used by rules that target nested fields like ``issuer.name`` or
``entity_ref.account_id``. Intentionally narrow: dotted-key descent into
mappings, with sequence indexing for purely numeric segments. Anything
more (wildcards, filters, slices) belongs in a real JSONPath library — not
here.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


_MISSING = object()


def normalize_path(path: str) -> str:
    """
    Return ``path`` with surrounding whitespace and a leading ``$.`` removed.

    Accepts ``"foo.bar"``, ``"$.foo.bar"``, ``"  foo.bar  "`` — all become
    ``"foo.bar"``. An empty path normalizes to the empty string and is
    treated as "the data itself" by ``get_path``.
    """
    if not isinstance(path, str):
        raise TypeError(f"path must be a string, got {type(path).__name__}")
    p = path.strip()
    if p.startswith("$."):
        p = p[2:]
    elif p == "$":
        p = ""
    return p


def get_path(data: Any, path: str, default: Any = None) -> Any:
    """
    Read the value at ``path`` from a nested mapping/sequence ``data``.

    A purely numeric segment indexes into a sequence (``items.0.price``).
    Any missing intermediate or final segment returns ``default`` — the
    helper never raises ``KeyError`` / ``IndexError`` for absent paths.

    For absolute clarity between "missing" and "explicit None", use
    ``path_exists`` alongside ``get_path``.
    """
    p = normalize_path(path)
    if p == "":
        return data
    current: Any = data
    for segment in p.split("."):
        current = _step(current, segment, default=_MISSING)
        if current is _MISSING:
            return default
    return current


def path_exists(data: Any, path: str) -> bool:
    """Return True if every segment of ``path`` resolves on ``data``."""
    return get_path(data, path, default=_MISSING) is not _MISSING


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------

def _step(value: Any, segment: str, *, default: Any) -> Any:
    if isinstance(value, Mapping):
        if segment in value:
            return value[segment]
        return default
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not segment.lstrip("-").isdigit():
            return default
        idx = int(segment)
        if -len(value) <= idx < len(value):
            return value[idx]
        return default
    return default
