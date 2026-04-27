"""
ValidationManifest — proof of what produced a result.

A manifest is the audit-and-replay receipt for a validation run. It
records the deterministic hash of every input that affected the result:
payload, ruleset, profile, contract snapshot, reference snapshots —
plus engine/runtime versions for reproducibility.

The hashes use ``validation_engine.core.hashing.stable_hash``, which is
SHA-256 over a canonical JSON form (sorted keys, normalized
``Decimal``/``datetime``/``Enum`` etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from ._immutable import freeze


@dataclass(frozen=True)
class ValidationManifest:
    validation_run_id: str
    request_id: str

    payload_hash: str
    ruleset_hash: str | None = None
    profile_hash: str | None = None
    contract_snapshot_hash: str | None = None
    reference_data_hashes: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    engine_version: str | None = None
    code_version: str | None = None
    python_version: str | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None

    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.reference_data_hashes, MappingProxyType):
            object.__setattr__(
                self, "reference_data_hashes", freeze(self.reference_data_hashes),
            )
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))
