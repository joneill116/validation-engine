"""Field-level partitioning strategy.

Publishes clean fields while holding dirty fields for stewardship.
Enables partial entity publication for maximum data availability.

Routing Logic:
- Clean fields → publish_target (partial entity with only good fields)
- Dirty fields → exception_target (for stewardship)

Designed for scenarios where partial data is valuable and tolerable.
"""
import copy
from types import MappingProxyType
from ..contracts.enums import ActionType
from ..contracts.actions import Action, StrategyDecision
from ..contracts.results import CollectionResult


class FieldPartitionStrategy:
    """
    Publishes clean fields immediately; raises exceptions for bad fields.

    An entity with mixed quality produces TWO actions:
      - PUBLISH  → clean fields (partial=True signals incomplete record)
      - RAISE_EXCEPTION → bad fields with their failures

    An entity with no failures produces one PUBLISH action (partial=False).
    An entity with no clean fields at all produces one RAISE_EXCEPTION only.

    This strategy is useful when partial records have downstream value and
    you don't want to block the good data while stewards resolve the bad.
    """

    strategy_id = "field_partition"
    version = "1.0"

    def __init__(self, publish_target: str, exception_target: str) -> None:
        self.publish_target = publish_target
        self.exception_target = exception_target

    def decide(self, result: CollectionResult) -> StrategyDecision:
        actions: list[Action] = []
        counts: dict[str, int] = {"publish": 0, "exception": 0}

        for e in result.entities:
            is_partial = bool(e.bad)

            # Deep copy values to prevent nested mutation bugs
            if e.good:
                actions.append(Action(
                    action_type=ActionType.PUBLISH,
                    entity_ref=e.entity_ref,
                    payload=MappingProxyType({
                        "fields": {k: copy.deepcopy(v.value) for k, v in e.good},
                        "partial": is_partial,
                    }),
                    target=self.publish_target,
                    rationale=f"{len(e.good)} clean field(s)"
                              + (f"; {len(e.bad)} field(s) withheld" if is_partial else ""),
                ))
                counts["publish"] += 1

            if e.bad:
                actions.append(Action(
                    action_type=ActionType.RAISE_EXCEPTION,
                    entity_ref=e.entity_ref,
                    payload=MappingProxyType({
                        "failed_fields": {
                            k: {
                                "value": copy.deepcopy(v.value),
                                "failures": [copy.deepcopy(f.__dict__) for f in v.failures],
                            }
                            for k, v in e.bad
                        },
                        "entity_findings": [copy.deepcopy(f.__dict__) for f in e.entity_findings if not f.passed],
                    }),
                    target=self.exception_target,
                    rationale=f"{len(e.bad)} field(s) failed validation",
                ))
                counts["exception"] += 1

        return StrategyDecision(
            strategy_id=self.strategy_id,
            strategy_version=self.version,
            actions=tuple(actions),
            summary=MappingProxyType(counts),
        )
