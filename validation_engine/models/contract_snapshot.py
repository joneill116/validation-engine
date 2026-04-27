"""
ContractSnapshot — an immutable inbound contract definition.

The validation library is *not* a contract registry: it does not author,
approve, version, or publish contracts. It does, however, accept a
caller-resolved snapshot of a contract at validation time so it can:

  - check required fields are present
  - check field types match the contract
  - hash the contract into the result manifest

The lifecycle of the contract belongs entirely outside the library.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping

from ._immutable import freeze


# Logical types accepted in a contract field. Aligned with TypeCheckRule.
ContractFieldType = Literal[
    "string", "integer", "decimal", "boolean",
    "date", "datetime", "object", "array", "any",
]


@dataclass(frozen=True)
class ContractFieldSnapshot:
    field_path: str
    field_type: str = "any"
    required: bool = False
    nullable: bool = True
    semantic_type: str | None = None
    description: str = ""
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not self.field_path or not isinstance(self.field_path, str):
            raise ValueError("ContractFieldSnapshot.field_path is required")
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))


@dataclass(frozen=True)
class ContractSnapshot:
    contract_id: str
    contract_version: str
    entity_type: str

    fields: tuple[ContractFieldSnapshot, ...] = field(default_factory=tuple)
    required_entity_ref_keys: tuple[str, ...] = field(default_factory=tuple)

    source: str | None = None
    schema_version: str | None = None
    contract_hash: str | None = None
    retrieved_at: str | None = None

    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not self.contract_id:
            raise ValueError("ContractSnapshot.contract_id is required")
        if not self.contract_version:
            raise ValueError("ContractSnapshot.contract_version is required")
        if not self.entity_type:
            raise ValueError("ContractSnapshot.entity_type is required")
        if not isinstance(self.fields, tuple):
            object.__setattr__(self, "fields", tuple(self.fields))
        if not isinstance(self.required_entity_ref_keys, tuple):
            object.__setattr__(
                self, "required_entity_ref_keys",
                tuple(self.required_entity_ref_keys),
            )
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))
