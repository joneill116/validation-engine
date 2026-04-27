"""
ValidationProfile — the complete validation setup for a class of runs.

A profile binds a ruleset, defaults (severity, category), and the
expected contract / required reference data names to a profile_id. It is
purely declarative; the engine consumes it via the config layer like a
ruleset.

The profile **must not** contain operational concerns (publish topics,
quarantine, exception routing). Those belong on the strategy/decision
layer downstream.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from ._immutable import freeze
from .enums import Category, Severity
from .threshold import ThresholdPolicy


@dataclass(frozen=True)
class ValidationProfile:
    profile_id: str
    profile_version: str
    description: str = ""

    ruleset_id: str | None = None
    ruleset_version: str | None = None

    expected_contract_id: str | None = None
    expected_contract_version: str | None = None

    required_reference_data: tuple[str, ...] = field(default_factory=tuple)

    default_severity: Severity = Severity.BLOCKING
    default_category: Category = Category.BUSINESS_RULE

    # Map of policy_id -> ThresholdPolicy. Rules look these up by name
    # via ``ctx.get_threshold_policy(policy_id)``.
    threshold_policies: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id:
            raise ValueError("ValidationProfile.profile_id is required")
        if not isinstance(self.profile_version, str) or not self.profile_version:
            raise ValueError("ValidationProfile.profile_version is required")
        if not isinstance(self.required_reference_data, tuple):
            object.__setattr__(self, "required_reference_data", tuple(self.required_reference_data))
        # Validate threshold_policies values are actual ThresholdPolicy
        # objects so misconfiguration shows up at construction time, not
        # when a rule first reaches in to use one.
        for name, policy in self.threshold_policies.items():
            if not isinstance(policy, ThresholdPolicy):
                raise TypeError(
                    f"threshold_policies[{name!r}] must be a ThresholdPolicy, "
                    f"got {type(policy).__name__}"
                )
        if not isinstance(self.threshold_policies, MappingProxyType):
            object.__setattr__(self, "threshold_policies", freeze(self.threshold_policies))
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", freeze(self.metadata))
        # Coerce string severity/category passed by the YAML loader.
        if isinstance(self.default_severity, str) and not isinstance(self.default_severity, Severity):
            object.__setattr__(self, "default_severity", Severity(self.default_severity))
        if isinstance(self.default_category, str) and not isinstance(self.default_category, Category):
            object.__setattr__(self, "default_category", Category(self.default_category))

    def get_threshold_policy(self, policy_id: str) -> ThresholdPolicy | None:
        """Return the named threshold policy, or ``None`` if not present."""
        return self.threshold_policies.get(policy_id)
