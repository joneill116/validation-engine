"""
RulesetCompiler — turns a RulesetConfig into runnable rules + strategy.

The compiler is the bridge between the typed config schema and the
runtime engine. Given the same config it produces equivalent objects.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

from ..rules.base import Rule
from ..strategies.base import PublishStrategy
from ..strategies.partitioned import PartitionBy, PartitionedStrategy, PartitionFn
from ..strategies.severity_gate import SeverityGateStrategy
from .factory import RuleFactory
from .schema import RulesetConfig, StrategyConfig


StrategyBuilder = Callable[[StrategyConfig], PublishStrategy]


@dataclass(frozen=True)
class CompiledRuleset:
    """Output of the compiler — drop into ValidationEngine."""

    ruleset_id: str
    ruleset_version: str
    entity_type: str
    rules: tuple[Rule, ...]
    strategy: PublishStrategy
    reference_data: MappingProxyType


class RulesetCompiler:
    """
    Compiles ``RulesetConfig`` into ``CompiledRuleset``.

    Args:
        rule_factory: Factory used to instantiate rules. Defaults to a
            new ``RuleFactory()`` with standard rule types registered.
        strategy_builder: Callable that returns a strategy given a
            ``StrategyConfig``. Defaults to the built-in builder which
            knows about ``severity_gate``.
        config_dir: Directory used to resolve relative ``reference_data``
            paths. If omitted, only absolute paths are honoured.
    """

    def __init__(
        self,
        rule_factory: RuleFactory | None = None,
        strategy_builder: StrategyBuilder | None = None,
        config_dir: str | os.PathLike | None = None,
    ) -> None:
        self._factory = rule_factory or RuleFactory()
        self._strategy_builder = strategy_builder or _default_strategy_builder
        self._config_dir = Path(config_dir) if config_dir else None

    def compile(self, cfg: RulesetConfig) -> CompiledRuleset:
        enabled_rules = [r for r in cfg.rules if r.enabled]
        _check_duplicate_rule_ids(enabled_rules)
        _validate_dependency_graph(enabled_rules)
        rules = tuple(self._factory.build(r) for r in enabled_rules)
        strategy = self._strategy_builder(cfg.strategy)
        reference_data = self._load_reference_data(cfg)
        return CompiledRuleset(
            ruleset_id=cfg.ruleset_id,
            ruleset_version=cfg.ruleset_version,
            entity_type=cfg.entity_type,
            rules=rules,
            strategy=strategy,
            reference_data=MappingProxyType(reference_data),
        )

    # ------------------------------------------------------------------

    def _load_reference_data(self, cfg: RulesetConfig) -> dict[str, Any]:
        from collections.abc import Mapping as _Mapping  # local to keep top imports tidy
        out: dict[str, Any] = {}
        for ref in cfg.reference_data:
            if ref.inline is not None:
                # Accept any shape — the engine treats reference data as
                # opaque values keyed by ``name``. Mappings get dict-copied
                # to detach from the config object; everything else is
                # stored as-is.
                out[ref.name] = dict(ref.inline) if isinstance(ref.inline, _Mapping) else ref.inline
                continue
            if not ref.path:
                raise ValueError(
                    f"reference_data {ref.name!r}: provide 'inline' or 'path'"
                )
            p = Path(ref.path)
            if not p.is_absolute() and self._config_dir is not None:
                p = self._config_dir / p
            if not p.exists():
                raise FileNotFoundError(
                    f"reference_data {ref.name!r}: file not found at {p}"
                )
            out[ref.name] = _read_data_file(p)
        return out


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _check_duplicate_rule_ids(rules) -> None:
    """Reject rulesets that contain two enabled rules with the same rule_id."""
    seen: dict[str, int] = {}
    for r in rules:
        seen[r.rule_id] = seen.get(r.rule_id, 0) + 1
    duplicates = [rid for rid, count in seen.items() if count > 1]
    if duplicates:
        raise ValueError(
            f"Duplicate rule_id(s) in ruleset: {sorted(duplicates)!r}. "
            f"Rule ids must be unique within a ruleset for traceable findings."
        )


def _validate_dependency_graph(rules) -> None:
    """
    Validate ``depends_on`` references at compile time.

    Catches two authoring mistakes:
      - reference to a rule_id that doesn't exist (typo / missing rule)
      - dependency cycles (rule A -> B -> A would deadlock the engine)
    """
    rule_ids = {r.rule_id for r in rules}
    # 1. Missing references.
    for r in rules:
        for dep in r.depends_on:
            if dep.rule_id not in rule_ids:
                raise ValueError(
                    f"Rule {r.rule_id!r} depends on unknown rule {dep.rule_id!r}. "
                    f"Available rule_ids: {sorted(rule_ids)!r}"
                )
    # 2. Cycles via DFS with recursion stack.
    graph: dict[str, list[str]] = {r.rule_id: [d.rule_id for d in r.depends_on] for r in rules}
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[str, int] = {rid: WHITE for rid in graph}

    def visit(node: str, path: list[str]) -> None:
        colour[node] = GREY
        for neighbour in graph.get(node, []):
            if colour[neighbour] == GREY:
                cycle = path[path.index(neighbour):] + [neighbour]
                raise ValueError(
                    f"Dependency cycle detected: {' -> '.join(cycle)}"
                )
            if colour[neighbour] == WHITE:
                visit(neighbour, path + [neighbour])
        colour[node] = BLACK

    for node in graph:
        if colour[node] == WHITE:
            visit(node, [node])


def _read_data_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ImportError(
                f"PyYAML required to load {path}. Install with: pip install pyyaml"
            ) from exc
        return yaml.safe_load(text)
    if suffix == ".json":
        return json.loads(text)
    raise ValueError(f"Unsupported reference_data file extension: {suffix}")


def _default_strategy_builder(strategy_config: StrategyConfig) -> PublishStrategy:
    stype = strategy_config.strategy_type
    params = dict(strategy_config.params or {})

    if stype == SeverityGateStrategy.strategy_id:
        return _build_severity_gate(params)
    if stype == PartitionedStrategy.strategy_id:
        return _build_partitioned(params)
    raise KeyError(
        f"Unknown strategy_type {stype!r}. "
        f"Pass a custom strategy_builder to RulesetCompiler() to support it."
    )


def _build_severity_gate(params: dict) -> SeverityGateStrategy:
    return SeverityGateStrategy(
        publish_target=params.get("publish_target", "publish"),
        quarantine_target=params.get("quarantine_target", "quarantine"),
        exception_target=params.get("exception_target", "exception"),
        warnings_target=params.get("warnings_target"),
        on_blocking=params.get("on_blocking", "route_to_exception"),
        on_error=params.get("on_error", "halt"),
    )


def _build_partitioned(params: dict) -> PartitionedStrategy:
    inner_cfg = params.get("inner")
    if not isinstance(inner_cfg, dict):
        raise ValueError(
            "partitioned strategy requires an 'inner' strategy config "
            "(e.g. {'strategy_type': 'severity_gate', 'params': {...}})"
        )
    inner = _default_strategy_builder(StrategyConfig(
        strategy_type=inner_cfg.get("strategy_type", "severity_gate"),
        params=inner_cfg.get("params") or {},
    ))
    raw = params.get("partition_by")
    if raw is None:
        raise ValueError("partitioned strategy requires 'partition_by'")
    partition_fn = _parse_partition_by(raw)
    return PartitionedStrategy(
        inner=inner,
        partition_by=partition_fn,
        dimension=params.get("dimension"),
    )


def _parse_partition_by(raw: Any) -> PartitionFn:
    """
    Parse the YAML/dict ``partition_by`` config into a PartitionFn.

    Accepted forms (``X`` is any caller-chosen key — the framework does
    not assign meaning to it):
      - ``"X"``                       sugar for ``entity_ref.X``
      - ``"entity_ref.X"``            explicit entity_ref key
      - ``"fields.X"``                value of a field on the entity
      - ``"field_path"``              which field path produced the finding
      - ``["entity_ref.X", "fields.Y", ...]``   multi-key tuple
    """
    if isinstance(raw, list):
        if not raw:
            raise ValueError("partition_by list cannot be empty")
        return PartitionBy.combine(*(_parse_partition_by(item) for item in raw))
    if not isinstance(raw, str):
        raise ValueError(
            f"partition_by must be a string or list of strings, got {type(raw).__name__}"
        )
    if raw == "field_path":
        return PartitionBy.field_path()
    if "." in raw:
        source, _, key = raw.partition(".")
        if source == "entity_ref":
            return PartitionBy.entity_ref(key)
        if source == "fields":
            return PartitionBy.field(key)
        raise ValueError(
            f"partition_by source {source!r} unknown (use 'entity_ref' or 'fields')"
        )
    # Bare string -> default to entity_ref key
    return PartitionBy.entity_ref(raw)
