"""
ReferenceDataSnapshot — an immutable inbound reference data set.

The validation library does not own reference data: it does not fetch,
store, or govern lookup tables. It accepts a caller-resolved snapshot at
validation time so rules can read it via ``ctx.get_reference_data(name)``
and the engine can hash it into the result manifest.

A ``ReferenceDataSnapshot`` is identified by ``name`` plus ``version``
(when provided) so the same logical reference table at two points in
time produces two distinct snapshot hashes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from ._immutable import freeze


@dataclass(frozen=True)
class ReferenceDataSnapshot:
    name: str
    # ``data`` is whatever the caller wants the engine to expose at the
    # snapshot's ``name``. A list of allowed values, a dict keyed by code,
    # a single scalar, etc. The engine treats it as opaque: the caller
    # decides the shape and rules read it via ``ctx.get_reference_data``.
    data: Any

    version: str | None = None
    source: str | None = None
    snapshot_hash: str | None = None
    retrieved_at: str | None = None
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ReferenceDataSnapshot.name is required")
        # Freeze mapping data so callers can hand us a regular dict and
        # not accidentally mutate it after the snapshot is hashed. Other
        # shapes (list/tuple/scalar) we leave alone — they're already
        # immutable enough or under the caller's control.
        if isinstance(self.data, Mapping) and not isinstance(self.data, MappingProxyType):
            object.__setattr__(self, "data", freeze(self.data))
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))
