from typing import Protocol, runtime_checkable
from ..contracts.results import CollectionResult
from ..contracts.actions import StrategyDecision


@runtime_checkable
class PublishStrategy(Protocol):
    strategy_id: str
    version: str

    def decide(self, result: CollectionResult) -> StrategyDecision: ...
