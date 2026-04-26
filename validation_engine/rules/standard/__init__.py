"""
Standard configurable rule implementations.

Each module exports one rule class registered against a ``rule_type``
string used in YAML/JSON configs.
"""
from .required import RequiredRule
from .not_null import NotNullRule
from .enum_rule import EnumRule
from .range_rule import RangeRule
from .regex_rule import RegexRule
from .comparison import ComparisonRule
from .date_between import DateBetweenRule
from .unique import UniqueRule
from .conditional_required import ConditionalRequiredRule
from .sum_equals import SumEqualsRule

# Registry mapping rule_type -> class
STANDARD_RULES = {
    RequiredRule.rule_type: RequiredRule,
    NotNullRule.rule_type: NotNullRule,
    EnumRule.rule_type: EnumRule,
    RangeRule.rule_type: RangeRule,
    RegexRule.rule_type: RegexRule,
    ComparisonRule.rule_type: ComparisonRule,
    DateBetweenRule.rule_type: DateBetweenRule,
    UniqueRule.rule_type: UniqueRule,
    ConditionalRequiredRule.rule_type: ConditionalRequiredRule,
    SumEqualsRule.rule_type: SumEqualsRule,
}

__all__ = [
    "RequiredRule",
    "NotNullRule",
    "EnumRule",
    "RangeRule",
    "RegexRule",
    "ComparisonRule",
    "DateBetweenRule",
    "UniqueRule",
    "ConditionalRequiredRule",
    "SumEqualsRule",
    "STANDARD_RULES",
]
