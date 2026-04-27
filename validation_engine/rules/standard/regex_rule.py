"""
RegexRule — asserts a string field matches a regular expression.
"""
from __future__ import annotations

import re
from typing import Any

from ...core.context import EvaluationContext
from ...models.enums import Category, Scope
from ...models.finding import ValidationFinding
from ...models import finding_codes
from ..configured import ConfiguredRule


class RegexRule(ConfiguredRule):
    rule_type = "regex"
    finding_code = finding_codes.INVALID_FORMAT

    def __init__(self, rule_id: str, **kwargs) -> None:
        kwargs.setdefault("scope", Scope.FIELD)
        kwargs.setdefault("category", Category.STRUCTURAL)
        super().__init__(rule_id, **kwargs)
        pattern = self.params.get("pattern")
        if not pattern:
            raise ValueError(
                f"RegexRule {rule_id!r}: 'pattern' parameter is required"
            )
        flags = 0
        if self.params.get("ignore_case"):
            flags |= re.IGNORECASE
        if self.params.get("multiline"):
            flags |= re.MULTILINE
        self._pattern_text = pattern
        self._regex = re.compile(pattern, flags)
        self._full_match = bool(self.params.get("full_match", True))

    def evaluate(self, target: Any, ctx: EvaluationContext) -> ValidationFinding:
        if not isinstance(target, str):
            return self.make_finding(
                passed=False,
                message=self._message(
                    f"Field {self.field_path!r} must be a string for regex match"
                ),
                    expected=f"string matching {self._pattern_text!r}",
                actual=target,
            )
        match_fn = self._regex.fullmatch if self._full_match else self._regex.search
        passed = bool(match_fn(target))
        return self.make_finding(
            passed=passed,
            message=self._message(
                f"Value {target!r} does not match pattern {self._pattern_text!r}"
            ) if not passed else f"Value matches pattern",
            expected=self._pattern_text,
            actual=target,
        )
