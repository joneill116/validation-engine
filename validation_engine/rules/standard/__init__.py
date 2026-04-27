"""
Standard configurable rule implementations.

Each module exports one rule class registered against a ``rule_type``
string used in YAML/JSON configs.
"""
from .comparison import ComparisonRule
from .completeness_ratio import CompletenessRatioRule
from .conditional_required import ConditionalRequiredRule
from .date_between import DateBetweenRule
from .enum_rule import EnumRule
from .not_null import NotNullRule
from .range_rule import RangeRule
from .record_count import RecordCountRule
from .regex_rule import RegexRule
from .required import RequiredRule
from .sum_equals import SumEqualsRule
from .type_check import TypeCheckRule
from .unique import UniqueRule

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
    TypeCheckRule.rule_type: TypeCheckRule,
    RecordCountRule.rule_type: RecordCountRule,
    CompletenessRatioRule.rule_type: CompletenessRatioRule,
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
    "TypeCheckRule",
    "RecordCountRule",
    "CompletenessRatioRule",
    "STANDARD_RULES",
]
