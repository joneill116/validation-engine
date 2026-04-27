"""
RuleDependency — rule-level prerequisites.

A rule may depend on another rule's outcome. The compiler validates the
graph (no missing rule_ids, no cycles) and the engine sequences rules so
dependents only run after their prerequisites have produced a result.

Modes:
  - ``REQUIRES_PASS`` (default): the dependency must have run and passed.
    Failed/Errored/Skipped/NotApplicable dependencies cause this rule to
    be SKIPPED with a ``skip_reason`` of ``dependency_failed``.
  - ``REQUIRES_RUN``: the dependency must have run (any outcome except
    SKIPPED / NOT_APPLICABLE / ERROR — pass or fail is fine).
  - ``SKIP_IF_FAILED``: the rule runs unless the dependency failed/errored.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DependencyMode(str, Enum):
    REQUIRES_PASS = "requires_pass"
    REQUIRES_RUN = "requires_run"
    SKIP_IF_FAILED = "skip_if_failed"


@dataclass(frozen=True)
class RuleDependency:
    rule_id: str
    mode: DependencyMode = DependencyMode.REQUIRES_PASS

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, str) or not self.rule_id:
            raise ValueError("RuleDependency.rule_id must be a non-empty string")
        if not isinstance(self.mode, DependencyMode):
            object.__setattr__(self, "mode", DependencyMode(self.mode))
