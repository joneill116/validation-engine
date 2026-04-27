"""
JSON-friendly serialization for public models.

``to_jsonable`` and ``from_jsonable`` provide a stable, lossless-as-far-as-
practical round-trip for the model layer. Designed so any frozen dataclass
in ``validation_engine.models`` can be persisted, replayed, diffed, and
golden-tested without bespoke per-model code.

Round-trip semantics:
    obj  ──to_jsonable──▶  json-friendly dict/list/scalar
                           (composed only of dict/list/str/int/float/bool/None)
    json ──from_jsonable──▶  obj of declared type

Type coercions on the ``from`` side are intentional: ``date``/``datetime``
revive from ISO-8601 strings, ``Decimal`` revives from its string form,
``Enum`` subclasses revive from their ``.value``, and tuples revive from
JSON lists where the dataclass field is annotated as a tuple.

Mappings other than ``dict``/``MappingProxyType`` are not supported in
typed fields — the public models only use those.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import typing
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Type, TypeVar, get_args, get_origin


T = TypeVar("T")


# ---------------------------------------------------------------------------
# obj -> json-friendly
# ---------------------------------------------------------------------------

def to_jsonable(value: Any) -> Any:
    """
    Convert ``value`` to a JSON-friendly Python tree.

    The result composes only ``dict`` / ``list`` / ``str`` / ``int`` /
    ``float`` / ``bool`` / ``None``. Sort order is *not* enforced — use
    ``hashing.canonical_json`` when you need a deterministic byte stream.
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"non-finite float cannot be serialized: {value!r}")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"non-finite Decimal cannot be serialized: {value!r}")
        return str(value)
    if isinstance(value, _dt.datetime):
        return value.isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (Mapping, MappingProxyType)):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    raise TypeError(
        f"cannot serialize value of type {type(value).__name__}: {value!r}"
    )


def to_json(value: Any, *, indent: int | None = None) -> str:
    """JSON-encode ``value`` after passing it through ``to_jsonable``."""
    return json.dumps(to_jsonable(value), ensure_ascii=False, indent=indent)


# ---------------------------------------------------------------------------
# json-friendly -> typed obj
# ---------------------------------------------------------------------------

def from_jsonable(cls: Type[T], data: Any) -> T:
    """
    Construct an instance of ``cls`` from a JSON-friendly tree.

    Supports:
      - frozen dataclasses (rebuilt by field name)
      - ``Enum`` subclasses (reconstructed from ``.value``)
      - ``date`` / ``datetime`` (parsed from ISO-8601 strings)
      - ``Decimal`` (parsed from its string form)
      - parameterized ``tuple[X, ...]`` / ``list[X]`` / ``dict[str, X]`` /
        ``Mapping[str, X]`` / ``MappingProxyType`` field annotations
      - ``X | Y`` unions (tries each member; first success wins)
      - ``Any`` (passes the value through unchanged)
    """
    return _decode(cls, data)


def from_json(cls: Type[T], raw: str) -> T:
    return from_jsonable(cls, json.loads(raw))


# ---------------------------------------------------------------------------
# decoder internals
# ---------------------------------------------------------------------------

def _decode(annotation: Any, data: Any) -> Any:
    if annotation is Any or annotation is None:
        return data

    # Handle Optional / Unions ("X | Y" or typing.Union).
    origin = get_origin(annotation)
    if origin is typing.Union or _is_pep604_union(annotation):
        return _decode_union(get_args(annotation), data)

    if isinstance(annotation, type):
        if data is None:
            return None
        if annotation in (str, int, float, bool):
            return annotation(data) if not isinstance(data, annotation) else data
        if annotation is Decimal:
            return Decimal(data) if not isinstance(data, Decimal) else data
        if annotation is _dt.datetime:
            return data if isinstance(data, _dt.datetime) else _dt.datetime.fromisoformat(data)
        if annotation is _dt.date:
            return data if isinstance(data, _dt.date) else _dt.date.fromisoformat(data)
        if issubclass(annotation, Enum):
            return annotation(data)
        if dataclasses.is_dataclass(annotation):
            return _decode_dataclass(annotation, data)

    if origin in (list, tuple, set, frozenset):
        args = get_args(annotation)
        elem_type = args[0] if args else Any
        decoded = [_decode(elem_type, v) for v in data]
        if origin is tuple:
            return tuple(decoded)
        if origin is set:
            return set(decoded)
        if origin is frozenset:
            return frozenset(decoded)
        return decoded

    if origin in (dict, Mapping, MappingProxyType) or annotation is MappingProxyType:
        args = get_args(annotation)
        val_type = args[1] if len(args) == 2 else Any
        decoded = {str(k): _decode(val_type, v) for k, v in data.items()}
        if origin is MappingProxyType or annotation is MappingProxyType:
            return MappingProxyType(decoded)
        return decoded

    # Fallback: leave the value alone (covers unparameterized typing.Mapping
    # etc. — the dataclass __post_init__ usually freezes/normalizes anyway).
    return data


def _decode_dataclass(cls: type, data: Any) -> Any:
    if not isinstance(data, Mapping):
        raise TypeError(
            f"cannot decode {cls.__name__} from {type(data).__name__}; expected mapping"
        )
    field_types = typing.get_type_hints(cls)
    init_kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if not f.init:
            continue
        if f.name not in data:
            # Let the dataclass default kick in.
            continue
        annotation = field_types.get(f.name, Any)
        init_kwargs[f.name] = _decode(annotation, data[f.name])
    return cls(**init_kwargs)


def _decode_union(args: tuple, data: Any) -> Any:
    # ``None`` matches ``type(None)`` directly.
    if data is None and type(None) in args:
        return None
    last_exc: Exception | None = None
    for member in args:
        if member is type(None):
            continue
        try:
            return _decode(member, data)
        except (TypeError, ValueError) as exc:
            last_exc = exc
            continue
    raise TypeError(
        f"value {data!r} does not match any union member {args}: {last_exc}"
    )


def _is_pep604_union(annotation: Any) -> bool:
    """Recognize PEP 604 ``X | Y`` unions on Python 3.10+."""
    return type(annotation).__name__ == "UnionType"
