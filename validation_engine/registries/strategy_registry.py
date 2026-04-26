"""
StrategyRegistry — maps strategy_id -> strategy instance.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..strategies.base import PublishStrategy


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, "PublishStrategy"] = {}

    def register(self, strategy: "PublishStrategy") -> None:
        sid = getattr(strategy, "strategy_id", None)
        if not sid or not isinstance(sid, str):
            raise ValueError(
                f"strategy must expose a non-empty 'strategy_id' string, got {sid!r}"
            )
        self._strategies[sid] = strategy

    def get(self, strategy_id: str) -> "PublishStrategy":
        strat = self._strategies.get(strategy_id)
        if strat is None:
            available = ", ".join(repr(s) for s in self._strategies)
            raise KeyError(
                f"No strategy registered for strategy_id={strategy_id!r}. "
                f"Available: {available or 'none'}"
            )
        return strat
