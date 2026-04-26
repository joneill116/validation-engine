"""
Config layer.

Pipeline:
    YAML/JSON config
        -> ConfigLoader (load)
        -> RulesetConfig (typed schema)
        -> RulesetCompiler (compile)
        -> CompiledRuleset (rules + strategy)
        -> ValidationEngine
"""
from .compiler import CompiledRuleset, RulesetCompiler
from .factory import RuleFactory
from .loader import ConfigLoadError, ConfigLoader, load_ruleset
from .schema import (
    ReferenceDataRef,
    RuleConfig,
    RulesetConfig,
    StrategyConfig,
)

__all__ = [
    "RuleConfig",
    "RulesetConfig",
    "StrategyConfig",
    "ReferenceDataRef",
    "ConfigLoader",
    "ConfigLoadError",
    "load_ruleset",
    "RuleFactory",
    "RulesetCompiler",
    "CompiledRuleset",
]
