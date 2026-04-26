import copy
from types import MappingProxyType
from ..contracts.enums import Severity, ActionType, Disposition
from ..contracts.actions import Action, StrategyDecision
from ..contracts.results import CollectionResult


class SeverityGateStrategy:
    """
    Whole-entity gate based on severity_max.

    - INFO / WARNING  → PUBLISH (warnings included as tags in payload)
    - BLOCKING        → RAISE_EXCEPTION to exception_target
    - FATAL           → RAISE_EXCEPTION to urgent_target
    - Any BLOCKING/FATAL collection finding → HOLD entire batch

    Targets are logical identifiers (topic names, queue names, etc.).
    The caller decides what to do with each action.
    """

    strategy_id = "severity_gate"
    version = "1.0"

    def __init__(
        self,
        publish_target: str,
        exception_target: str,
        urgent_target: str | None = None,
    ) -> None:
        self.publish_target = publish_target
        self.exception_target = exception_target
        self.urgent_target = urgent_target or exception_target

    def decide(self, result: CollectionResult) -> StrategyDecision:
        collection_blockers = [
            f for f in result.collection_findings
            if not f.passed and f.severity in (Severity.BLOCKING, Severity.FATAL)
        ]

        if collection_blockers:
            actions = [
                Action(
                    action_type=ActionType.HOLD,
                    entity_ref=e.entity_ref,
                    payload=MappingProxyType({"entity": self._flatten_good(e)}),
                    target=self.exception_target,
                    rationale=f"Collection rule failed: {collection_blockers[0].rule_id}",
                )
                for e in result.entities
            ]
            return StrategyDecision(
                strategy_id=self.strategy_id,
                strategy_version=self.version,
                actions=tuple(actions),
                summary=MappingProxyType({"held": len(actions), "reason": "collection_failure"}),
            )

        actions: list[Action] = []
        counts: dict[str, int] = {"publish": 0, "exception": 0, "urgent": 0}

        for e in result.entities:
            sev = e.severity_max
            # Deep copy values to prevent nested mutation bugs
            all_fields = {**{k: copy.deepcopy(v.value) for k, v in e.good},
                          **{k: copy.deepcopy(v.value) for k, v in e.bad}}

            if sev == Severity.FATAL:
                actions.append(Action(
                    action_type=ActionType.RAISE_EXCEPTION,
                    entity_ref=e.entity_ref,
                    payload=MappingProxyType({"entity": all_fields, "failures": [copy.deepcopy(f.__dict__) for f in e.all_failures()]}),
                    target=self.urgent_target,
                    rationale="Fatal severity — urgent stewardship required",
                ))
                counts["urgent"] += 1

            elif sev == Severity.BLOCKING:
                actions.append(Action(
                    action_type=ActionType.RAISE_EXCEPTION,
                    entity_ref=e.entity_ref,
                    payload=MappingProxyType({"entity": all_fields, "failures": [copy.deepcopy(f.__dict__) for f in e.all_failures()]}),
                    target=self.exception_target,
                    rationale="Blocking failures — stewardship required",
                ))
                counts["exception"] += 1

            else:
                actions.append(Action(
                    action_type=ActionType.PUBLISH,
                    entity_ref=e.entity_ref,
                    payload=MappingProxyType({"entity": all_fields, "warnings": [copy.deepcopy(f.__dict__) for f in e.warnings()]}),
                    target=self.publish_target,
                    rationale=f"Max severity {sev.value} — publishable",
                ))
                counts["publish"] += 1

        return StrategyDecision(
            strategy_id=self.strategy_id,
            strategy_version=self.version,
            actions=tuple(actions),
            summary=MappingProxyType(counts),
        )

    @staticmethod
    def _flatten_good(e) -> dict:
        """Extract good field values from tuple structure with deep copy."""
        return {k: copy.deepcopy(v.value) for k, v in e.good}
