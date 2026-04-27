"""
Validation Engine — a generic, configurable data quality framework.

Central contract::

    ValidationRequest
        -> ValidationEngine
        -> RuleResult
        -> ValidationFinding
        -> ValidationSummary
        -> ValidationDecision
        -> ValidationResult

Quick-start::

    from validation_engine import (
        ValidationEngine, ValidationRequest,
        load_ruleset, RulesetCompiler,
    )

    ruleset_config = load_ruleset("path/to/your/ruleset.yaml")
    compiled = RulesetCompiler().compile(ruleset_config)

    engine = ValidationEngine(
        rules=list(compiled.rules),
        strategy=compiled.strategy,
        reference_data=compiled.reference_data,
    )

    request = ValidationRequest(
        request_id="REQ-001",
        tenant_id="<your_tenant>",
        data_product_id="<your_data_product>",
        data_flow_id="<your_data_flow>",
        entity_type="<your_entity_type>",
        ruleset_id="<your_ruleset_id>",
        ruleset_version="v1",
        payload=payload,
    )

    result = engine.validate(request)
    print(result.status.value, result.decision.action.value, result.summary.failed_count)

The framework is fully domain-agnostic. Domain-specific rule classes
should live in the consuming application and be plugged in via
``RuleFactory.register_class(rule_type, RuleClass)``.
"""

# core engine + context
from .core.engine import ValidationEngine, PayloadValidationError
from .core.context import EvaluationContext

# models — input/output contract
from .models import finding_codes
from .models.enums import (
    BLOCKING_SEVERITIES,
    Category,
    DecisionAction,
    RuleEvaluationStatus,
    RuleExecutionStatus,
    Scope,
    Severity,
    ValidationStatus,
)
from .models.request import ValidationRequest
from .models.finding import ValidationFinding
from .models.observation import Observation
from .models.outcome import ValidationOutcome
from .models.profile import ValidationProfile
from .models.target import ValidationTarget
from .models.rule_evaluation import RuleEvaluation
from .models.applicability import (
    ApplicabilityPredicate,
    PredicateOperator,
    RuleApplicability,
)
from .models.dependency import DependencyMode, RuleDependency
from .models.contract_snapshot import ContractFieldSnapshot, ContractSnapshot
from .models.reference_data import ReferenceDataSnapshot
from .models.threshold import (
    ThresholdBand,
    ThresholdMode,
    ThresholdOperator,
    ThresholdPolicy,
)
from .models.plan import PlannedRule, ValidationPlan
from .models.manifest import ValidationManifest
from .models.rule_result import RuleResult
from .models.summary import ValidationSummary
from .models.decision import ValidationDecision
from .models.error import ValidationError
from .models.partition_decision import PartitionDecision
from .models.result import ValidationResult

# rule authoring
from .rules.base import Rule
from .rules.configured import ConfiguredRule

# strategies
from .strategies.base import PerPartitionStrategy, PublishStrategy
from .strategies.partitioned import PartitionBy, PartitionedStrategy, PartitionFn
from .strategies.severity_gate import SeverityGateStrategy

# config layer
from .config.schema import (
    ReferenceDataRef,
    RuleConfig,
    RulesetConfig,
    StrategyConfig,
)
from .config.loader import ConfigLoader, ConfigLoadError, load_ruleset
from .config.factory import RuleFactory
from .config.compiler import CompiledRuleset, RulesetCompiler

# registries
from .registries.rule_registry import RuleRegistry
from .registries.strategy_registry import StrategyRegistry

__version__ = "2.1.0"

__all__ = [
    # core
    "ValidationEngine",
    "EvaluationContext",
    "PayloadValidationError",
    # enums
    "BLOCKING_SEVERITIES",
    "Severity",
    "Scope",
    "Category",
    "ValidationStatus",
    "RuleExecutionStatus",
    "RuleEvaluationStatus",
    "DecisionAction",
    # models
    "ValidationRequest",
    "ValidationFinding",
    "Observation",
    "ValidationTarget",
    "ValidationOutcome",
    "ValidationProfile",
    "RuleResult",
    "RuleEvaluation",
    "RuleApplicability",
    "ApplicabilityPredicate",
    "PredicateOperator",
    "RuleDependency",
    "DependencyMode",
    "ContractSnapshot",
    "ContractFieldSnapshot",
    "ReferenceDataSnapshot",
    "ThresholdPolicy",
    "ThresholdBand",
    "ThresholdMode",
    "ThresholdOperator",
    "ValidationPlan",
    "PlannedRule",
    "ValidationManifest",
    "ValidationSummary",
    "ValidationDecision",
    "PartitionDecision",
    "ValidationError",
    "ValidationResult",
    # vocab
    "finding_codes",
    # rules
    "Rule",
    "ConfiguredRule",
    # strategies
    "PublishStrategy",
    "PerPartitionStrategy",
    "SeverityGateStrategy",
    "PartitionedStrategy",
    "PartitionBy",
    "PartitionFn",
    # config
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
    # registries
    "RuleRegistry",
    "StrategyRegistry",
    # version
    "__version__",
]
