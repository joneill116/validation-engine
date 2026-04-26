"""
ValidationRequest — the replayable input envelope for a validation run.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from ._immutable import freeze


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ValidationRequest:
    """
    Replayable, audit-friendly input envelope for a validation run.

    Fields:
        request_id: Unique identifier for this validation request.
        tenant_id: Multi-tenant isolation key.
        data_product_id: Logical data product the payload belongs to.
        data_flow_id: Pipeline / data flow within the data product.
        entity_type: Classification of the entities being validated.
        ruleset_id: Identifier of the ruleset to apply.
        ruleset_version: Version pin for the ruleset (audit trail).
        payload: Raw input data. Expected shape:
            {"entities": [{"entity_ref": {...}, "fields": {...}}, ...]}
        as_of_time: Business "as-of" timestamp (effective time of the data).
        as_at_time: System "as-at" timestamp (when the data was recorded).
        metadata: Free-form key/value pairs (tenant, source system, etc).
    """

    request_id: str = field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    tenant_id: str = "default"
    data_product_id: str = "default"
    data_flow_id: str = "default"
    entity_type: str = ""
    ruleset_id: str = ""
    ruleset_version: str = "latest"
    payload: dict[str, Any] = field(default_factory=dict)
    as_of_time: datetime = field(default_factory=_utc_now)
    as_at_time: datetime = field(default_factory=_utc_now)
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        # Validate required fields before paying for normalization.
        if not self.entity_type:
            raise ValueError("ValidationRequest.entity_type is required")
        if not self.ruleset_id:
            raise ValueError("ValidationRequest.ruleset_id is required")
        if not isinstance(self.payload, dict):
            object.__setattr__(self, "payload", dict(self.payload))
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))
