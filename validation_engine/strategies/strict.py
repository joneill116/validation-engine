import copy
from types import MappingProxyType
from ..contracts.enums import ActionType, Severity
from ..contracts.actions import Action, StrategyDecision
from ..contracts.results import CollectionResult


class StrictStrategy:
    """
    Any failure in any entity → HOLD the entire batch.

    Useful when downstream consumers require a complete, fully-validated
    collection before processing (e.g. fund NAV calculation, regulatory
    submissions) and partial data is worse than no data.

    If the batch is fully clean, all entities are published.
    """

    strategy_id = "strict"
    version = "1.0"

    def __init__(self, publish_target: str, hold_target: str) -> None:
        self.publish_target = publish_target
        self.hold_target = hold_target

    def decide(self, result: CollectionResult) -> StrategyDecision:
        any_failure = (
            any(e.bad or tuple(f for f in e.entity_findings if not f.passed) for e in result.entities)
            or any(not f.passed for f in result.collection_findings)
        )

        if any_failure:
            dirty = [
                e for e in result.entities
                if e.bad or any(not f.passed for f in e.entity_findings)
            ]
            dirty_refs = [e.entity_ref for e in dirty]

            # Deep copy values to prevent nested mutation bugs
            actions = [
                Action(
                    action_type=ActionType.HOLD,
                    entity_ref=e.entity_ref,
                    payload=MappingProxyType({
                        "entity": {**{k: copy.deepcopy(v.value) for k, v in e.good},
                                   **{k: copy.deepcopy(v.value) for k, v in e.bad}},
                        "failures": [copy.deepcopy(f.__dict__) for f in e.all_failures()],
                    }),
                    target=self.hold_target,
                    rationale=f"Strict mode: batch held — {len(dirty)} entity(s) failed",
                )
                for e in result.entities
            ]

            exception_action = Action(
                action_type=ActionType.RAISE_EXCEPTION,
                entity_ref=MappingProxyType({}),
                payload=MappingProxyType({"dirty_entity_refs": dirty_refs, "failure_count": len(dirty)}),
                target=self.hold_target,
                rationale="Strict mode: batch-level exception raised for failed entities",
            )
            actions.append(exception_action)

            return StrategyDecision(
                strategy_id=self.strategy_id,
                strategy_version=self.version,
                actions=tuple(actions),
                summary=MappingProxyType({"held": len(result.entities), "failed_entities": len(dirty)}),
            )

        # Deep copy values to prevent nested mutation bugs
        actions = [
            Action(
                action_type=ActionType.PUBLISH,
                entity_ref=e.entity_ref,
                payload=MappingProxyType({"entity": {k: copy.deepcopy(v.value) for k, v in e.good}}),
                target=self.publish_target,
                rationale="Strict mode: all entities clean",
            )
            for e in result.entities
        ]

        return StrategyDecision(
            strategy_id=self.strategy_id,
            strategy_version=self.version,
            actions=tuple(actions),
            summary=MappingProxyType({"publish": len(actions)}),
        )
