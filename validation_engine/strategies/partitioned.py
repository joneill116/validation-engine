"""
PartitionedStrategy — apply any inner strategy across any dimension.

A "dimension" is anything derivable from a finding plus the entity it
came from: a key in ``entity_ref``, a value from ``fields``, the field
path that failed, or any tuple combination thereof. The framework does
not care what those keys *mean*; the user names them.

The wrapped (inner) strategy is applied per partition, producing one
``PartitionDecision`` per slice. The run-level ``decide()`` returns a
worst-wins rollup so existing single-decision consumers still work.

Configuration form (Python)::

    PartitionedStrategy(
        inner=SeverityGateStrategy(...),
        partition_by=PartitionBy.entity_ref("group_key"),
    )

Or compose multi-key partitions::

    partition_by=PartitionBy.combine(
        PartitionBy.entity_ref("group_key"),
        PartitionBy.field("subgroup_key"),
    )
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Iterable, Mapping

from ..models.decision import ValidationDecision
from ..models.enums import DecisionAction
from ..models.error import ValidationError
from ..models.finding import ValidationFinding
from ..models.partition_decision import PartitionDecision
from ..models.summary import ValidationSummary
from .base import PublishStrategy


# A partitioner takes (entity, finding) and returns the partition key (a tuple).
# ``entity`` is the entity dict that produced the finding, or None when the
# finding is collection-scope (we exclude those from partitioning anyway).
# ``finding`` may be None when we're asking "what partition does this entity
# belong to" — used to seat clean entities (no findings) in their partition.
PartitionFn = Callable[
    [Mapping[str, Any] | None, ValidationFinding | None],
    tuple,
]


# ---------------------------------------------------------------------------
# Built-in partitioners
# ---------------------------------------------------------------------------

class PartitionBy:
    """Built-in partition functions and combinators."""

    @staticmethod
    def entity_ref(key: str) -> PartitionFn:
        """Partition by a key in the entity_ref dict."""
        def fn(entity, _finding):
            if entity is None:
                return (None,)
            ref = entity.get("entity_ref", {}) or {}
            return (ref.get(key),)
        fn.__qualname__ = f"PartitionBy.entity_ref({key!r})"
        fn.__dimension__ = f"entity_ref.{key}"  # type: ignore[attr-defined]
        return fn

    @staticmethod
    def field(name: str) -> PartitionFn:
        """Partition by a field value on the entity (supports rich field shape)."""
        def fn(entity, _finding):
            if entity is None:
                return (None,)
            fields = entity.get("fields", {}) or {}
            raw = fields.get(name)
            if isinstance(raw, dict) and "value" in raw:
                return (raw["value"],)
            return (raw,)
        fn.__qualname__ = f"PartitionBy.field({name!r})"
        fn.__dimension__ = f"fields.{name}"  # type: ignore[attr-defined]
        return fn

    @staticmethod
    def field_path() -> PartitionFn:
        """Partition by which field the finding was about."""
        def fn(_entity, finding):
            return (finding.field_path if finding is not None else None,)
        fn.__qualname__ = "PartitionBy.field_path()"
        fn.__dimension__ = "field_path"  # type: ignore[attr-defined]
        return fn

    @staticmethod
    def custom(fn: Callable, dimension: str = "custom") -> PartitionFn:
        """Wrap a user callable. Must return a tuple."""
        def wrapped(entity, finding):
            result = fn(entity, finding)
            return result if isinstance(result, tuple) else (result,)
        wrapped.__qualname__ = f"PartitionBy.custom({dimension!r})"
        wrapped.__dimension__ = dimension  # type: ignore[attr-defined]
        return wrapped

    @staticmethod
    def combine(*partitioners: PartitionFn) -> PartitionFn:
        """Concatenate keys from multiple partitioners (multi-dimensional)."""
        if not partitioners:
            raise ValueError("PartitionBy.combine() needs at least one partitioner")

        def fn(entity, finding):
            key: tuple = ()
            for p in partitioners:
                key = key + p(entity, finding)
            return key
        dims = ", ".join(getattr(p, "__dimension__", "?") for p in partitioners)
        fn.__qualname__ = f"PartitionBy.combine({dims})"
        fn.__dimension__ = f"({dims})"  # type: ignore[attr-defined]
        return fn


# ---------------------------------------------------------------------------
# The strategy
# ---------------------------------------------------------------------------

# Run-level rollup: if any partition needs intervention, the run signals it.
_INTERVENTION_ACTIONS = frozenset({
    DecisionAction.QUARANTINE,
    DecisionAction.ROUTE_TO_EXCEPTION,
    DecisionAction.HALT,
})


class PartitionedStrategy:
    """
    Decorator strategy: applies ``inner`` per partition.

    Run-level ``decide()`` delegates to ``inner`` with all findings
    (collection-scope findings included). Per-partition routing is in
    ``decide_per_partition()``, which the engine calls when the strategy
    implements the ``PerPartitionStrategy`` protocol.
    """

    strategy_id = "partitioned"

    def __init__(
        self,
        inner: PublishStrategy,
        partition_by: PartitionFn,
        dimension: str | None = None,
    ) -> None:
        self.inner = inner
        self.partition_by = partition_by
        self.dimension = dimension or getattr(partition_by, "__dimension__", "custom")

    # -- run-level (PublishStrategy) -----------------------------------

    def decide(
        self,
        findings: Iterable[ValidationFinding],
        errors: Iterable[ValidationError],
        summary: ValidationSummary,
    ) -> ValidationDecision:
        # Run-level: feed everything to the inner strategy as-is.
        return self.inner.decide(findings, errors, summary)

    # -- per-partition (PerPartitionStrategy) --------------------------

    def decide_per_partition(
        self,
        findings: Iterable[ValidationFinding],
        errors: Iterable[ValidationError],  # noqa: ARG002 (run-level only by design)
        summary: ValidationSummary,
        entities: tuple[Mapping[str, Any], ...],
    ) -> tuple[PartitionDecision, ...]:
        findings = tuple(findings)

        # 1. Map entity_ref -> entity dict so we can resolve a finding's entity.
        entity_lookup: dict[tuple, Mapping[str, Any]] = {}
        for entity in entities:
            ref = entity.get("entity_ref", {}) or {}
            entity_lookup[_hashable_ref(ref)] = entity

        # 2. Bucket entities by partition key (so clean entities still appear).
        buckets: dict[tuple, _Bucket] = defaultdict(_Bucket)
        for entity in entities:
            key = self.partition_by(entity, None)
            bucket = buckets[key]
            bucket.entity_count += 1

        # 3. Bucket findings by partition key. The engine pre-filters to
        #    entity/field-scope findings before calling us — collection-scope
        #    findings reach us via ``decide()`` and the run-level rollup.
        for f in findings:
            entity = entity_lookup.get(_hashable_ref(dict(f.entity_ref)))
            if entity is None:
                continue  # finding's entity_ref doesn't match any known entity
            key = self.partition_by(entity, f)
            bucket = buckets[key]
            bucket.findings.append(f)
            if not f.passed:
                bucket.failed_count += 1

        # 4. Apply the inner strategy to each partition's slice.
        out: list[PartitionDecision] = []
        for key, bucket in buckets.items():
            decision = self.inner.decide(
                tuple(bucket.findings),
                (),  # by design: collection-scope errors do not partition
                summary,
            )
            out.append(PartitionDecision(
                dimension=self.dimension,
                key=key,
                decision=decision,
                entity_count=bucket.entity_count,
                finding_count=len(bucket.findings),
                failed_count=bucket.failed_count,
            ))
        return tuple(out)


class _Bucket:
    __slots__ = ("entity_count", "findings", "failed_count")

    def __init__(self) -> None:
        self.entity_count = 0
        self.findings: list[ValidationFinding] = []
        self.failed_count = 0


def _hashable_ref(ref: Mapping[str, Any]) -> tuple:
    """Stable hashable key for an entity_ref mapping."""
    return tuple(sorted(ref.items())) if ref else ()
