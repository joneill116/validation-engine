"""Tests for the PartitionedStrategy decorator."""
import pytest

from validation_engine import (
    Category,
    DecisionAction,
    EvaluationContext,
    PartitionBy,
    PartitionedStrategy,
    Rule,
    Scope,
    Severity,
    SeverityGateStrategy,
    ValidationEngine,
    ValidationFinding,
    ValidationRequest,
)


# ------------------------------------------------------------------ helpers


class _AmountIsNumber(Rule):
    rule_id = "r.numeric_amount"
    rule_version = "1.0"
    scope = Scope.FIELD
    severity = Severity.BLOCKING
    category = Category.STRUCTURAL
    field_path = "amount"
    applies_to = frozenset({"*"})

    def evaluate(self, target, ctx: EvaluationContext) -> ValidationFinding:
        ok = isinstance(target, (int, float)) and not isinstance(target, bool)
        return self.make_finding(
            passed=ok,
            message=f"amount {target!r} is not numeric" if not ok else "ok",
            actual=target,
        )


def _engine(rules, strategy):
    return ValidationEngine(rules=rules, strategy=strategy)


def _request(entities):
    return ValidationRequest(
        entity_type="record", ruleset_id="rs1",
        payload={"entities": entities},
    )


def _strategy(partition_by):
    return PartitionedStrategy(
        inner=SeverityGateStrategy(
            publish_target="topic.publish",
            exception_target="topic.exception",
        ),
        partition_by=partition_by,
    )


# ------------------------------------------------------------------ tests


class TestPerEntityPartition:
    """Each entity is its own partition."""

    def test_clean_entity_publishes_bad_entity_routes_to_exception(self):
        entities = [
            {"entity_ref": {"id": "r1"}, "fields": {"amount": 100}},
            {"entity_ref": {"id": "r2"}, "fields": {"amount": "BAD"}},
            {"entity_ref": {"id": "r3"}, "fields": {"amount": 50}},
        ]
        engine = _engine([_AmountIsNumber()], _strategy(PartitionBy.entity_ref("id")))
        result = engine.validate(_request(entities))

        assert len(result.partition_decisions) == 3
        by_key = {pd.key: pd for pd in result.partition_decisions}
        assert by_key[("r1",)].action is DecisionAction.PUBLISH
        assert by_key[("r2",)].action is DecisionAction.ROUTE_TO_EXCEPTION
        assert by_key[("r3",)].action is DecisionAction.PUBLISH

    def test_run_level_decision_signals_intervention_needed(self):
        # One bad entity makes the run-level decision route_to_exception.
        entities = [
            {"entity_ref": {"id": "r1"}, "fields": {"amount": 100}},
            {"entity_ref": {"id": "r2"}, "fields": {"amount": "BAD"}},
        ]
        engine = _engine([_AmountIsNumber()], _strategy(PartitionBy.entity_ref("id")))
        result = engine.validate(_request(entities))
        assert result.decision.action is DecisionAction.ROUTE_TO_EXCEPTION


class TestCleanEntitiesIncluded:
    """Choice 1A: every entity appears in partition_decisions, even if it had no findings."""

    def test_entities_with_zero_findings_get_publish_partition(self):
        entities = [
            # No fields → AmountIsNumber doesn't fire on these
            {"entity_ref": {"id": "r1"}, "fields": {}},
            {"entity_ref": {"id": "r2"}, "fields": {}},
            {"entity_ref": {"id": "r3"}, "fields": {"amount": 100}},
        ]
        engine = _engine([_AmountIsNumber()], _strategy(PartitionBy.entity_ref("id")))
        result = engine.validate(_request(entities))
        assert len(result.partition_decisions) == 3
        for pd in result.partition_decisions:
            assert pd.action is DecisionAction.PUBLISH


class TestPerGroupPartition:
    """The headline use case: one bad group doesn't poison the others."""

    def test_one_bad_group_does_not_block_other_groups(self):
        entities = [
            {"entity_ref": {"id": "r1", "group": "A"}, "fields": {"amount": 100}},
            {"entity_ref": {"id": "r2", "group": "A"}, "fields": {"amount": 200}},
            {"entity_ref": {"id": "r3", "group": "B"}, "fields": {"amount": "BAD"}},
            {"entity_ref": {"id": "r4", "group": "C"}, "fields": {"amount": 50}},
        ]
        engine = _engine(
            [_AmountIsNumber()],
            _strategy(PartitionBy.entity_ref("group")),
        )
        result = engine.validate(_request(entities))

        by_key = {pd.key: pd for pd in result.partition_decisions}
        assert by_key[("A",)].action is DecisionAction.PUBLISH
        assert by_key[("A",)].entity_count == 2
        assert by_key[("B",)].action is DecisionAction.ROUTE_TO_EXCEPTION
        assert by_key[("C",)].action is DecisionAction.PUBLISH


class TestTupleKeyPartition:
    """Multi-dimensional partitioning: (key_a, key_b)."""

    def test_combine_produces_tuple_key(self):
        entities = [
            {"entity_ref": {"group": "A"}, "fields": {"bucket": "X", "amount": 100}},
            {"entity_ref": {"group": "A"}, "fields": {"bucket": "Y", "amount": "BAD"}},
            {"entity_ref": {"group": "B"}, "fields": {"bucket": "X", "amount": 50}},
        ]
        partition_by = PartitionBy.combine(
            PartitionBy.entity_ref("group"),
            PartitionBy.field("bucket"),
        )
        engine = _engine([_AmountIsNumber()], _strategy(partition_by))
        result = engine.validate(_request(entities))

        keys = {pd.key for pd in result.partition_decisions}
        assert ("A", "X") in keys
        assert ("A", "Y") in keys
        assert ("B", "X") in keys

        by_key = {pd.key: pd for pd in result.partition_decisions}
        assert by_key[("A", "Y")].action is DecisionAction.ROUTE_TO_EXCEPTION
        assert by_key[("A", "X")].action is DecisionAction.PUBLISH


class TestFieldPathPartition:
    """Partition by which field had the issue."""

    def test_field_path_partitions(self):
        # Two rules hitting different fields; partition by field_path.
        class AmountRule(_AmountIsNumber):
            rule_id = "r.amt"
            field_path = "amount"

        class CodeRule(Rule):
            rule_id = "r.code"
            rule_version = "1.0"
            scope = Scope.FIELD
            severity = Severity.BLOCKING
            category = Category.STRUCTURAL
            field_path = "code"
            applies_to = frozenset({"*"})
            def evaluate(self, target, ctx):
                ok = target in {"X", "Y"}
                return self.make_finding(
                    passed=ok, message="bad code" if not ok else "ok", actual=target,
                )

        entities = [
            {"entity_ref": {"id": "r1"}, "fields": {"amount": "BAD", "code": "X"}},
            {"entity_ref": {"id": "r2"}, "fields": {"amount": 100, "code": "ZZ"}},
        ]
        engine = _engine(
            [AmountRule(), CodeRule()],
            _strategy(PartitionBy.field_path()),
        )
        result = engine.validate(_request(entities))
        by_key = {pd.key: pd for pd in result.partition_decisions}
        # Each field with a finding gets its own partition
        assert ("amount",) in by_key
        assert ("code",) in by_key
        assert by_key[("amount",)].action is DecisionAction.ROUTE_TO_EXCEPTION
        assert by_key[("code",)].action is DecisionAction.ROUTE_TO_EXCEPTION


class TestEntityWithoutEntityRef:
    """Findings on entities with no/empty entity_ref must still partition.

    Regression: previously the partition strategy filtered findings by
    ``if not f.entity_ref: continue``, which conflated collection-scope
    findings (which have no entity) with entity-scope findings whose
    entity happened to lack an entity_ref. The latter were silently
    dropped from per-partition routing — a real data-quality miss.
    """

    def test_finding_on_entity_without_entity_ref_still_routes(self):
        # Entity carries no entity_ref at all.
        entities = [{"fields": {"amount": "BAD"}}]
        engine = _engine([_AmountIsNumber()], _strategy(PartitionBy.entity_ref("any_key")))
        result = engine.validate(_request(entities))

        assert len(result.partition_decisions) == 1
        pd = result.partition_decisions[0]
        assert pd.entity_count == 1
        assert pd.finding_count == 1
        assert pd.failed_count == 1
        assert pd.action is DecisionAction.ROUTE_TO_EXCEPTION


class TestNonPartitionedStrategy:
    """Plain SeverityGateStrategy: partition_decisions is empty."""

    def test_severity_gate_alone_produces_no_partition_decisions(self):
        engine = ValidationEngine(
            rules=[_AmountIsNumber()],
            strategy=SeverityGateStrategy(),
        )
        result = engine.validate(_request([
            {"entity_ref": {"id": "x"}, "fields": {"amount": 100}},
        ]))
        assert result.partition_decisions == ()


class TestYamlConfig:
    """The partitioned strategy should be configurable via YAML."""

    def setup_method(self):
        try:
            import yaml  # noqa: F401
            self._yaml_ok = True
        except ImportError:
            self._yaml_ok = False

    def test_yaml_partitioned_strategy_compiles(self):
        if not self._yaml_ok:
            pytest.skip("PyYAML not installed")
        from validation_engine import ConfigLoader, RulesetCompiler

        yaml_text = """
ruleset_id: rs1
ruleset_version: v1
entity_type: record
strategy:
  strategy_type: partitioned
  params:
    partition_by: entity_ref.group
    inner:
      strategy_type: severity_gate
      params:
        publish_target: topic.publish
        exception_target: topic.exception
rules: []
"""
        cfg = ConfigLoader().loads(yaml_text, fmt="yaml")
        compiled = RulesetCompiler().compile(cfg)
        assert isinstance(compiled.strategy, PartitionedStrategy)

    def test_yaml_tuple_partition(self):
        if not self._yaml_ok:
            pytest.skip("PyYAML not installed")
        from validation_engine import ConfigLoader, RulesetCompiler

        yaml_text = """
ruleset_id: rs1
ruleset_version: v1
entity_type: record
strategy:
  strategy_type: partitioned
  params:
    partition_by: [entity_ref.group, fields.bucket]
    inner:
      strategy_type: severity_gate
      params: {publish_target: p, exception_target: e}
rules: []
"""
        cfg = ConfigLoader().loads(yaml_text, fmt="yaml")
        compiled = RulesetCompiler().compile(cfg)
        # Construct a fake partition fn call to verify both keys
        fake_entity = {
            "entity_ref": {"group": "G1"},
            "fields": {"bucket": "B1"},
        }
        key = compiled.strategy.partition_by(fake_entity, None)
        assert key == ("G1", "B1")
