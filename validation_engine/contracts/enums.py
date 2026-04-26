from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"
    FATAL = "fatal"

    def __lt__(self, other: "Severity") -> bool:
        _order = [Severity.INFO, Severity.WARNING, Severity.BLOCKING, Severity.FATAL]
        return _order.index(self) < _order.index(other)

    def __le__(self, other: "Severity") -> bool:
        return self == other or self < other

    def __gt__(self, other: "Severity") -> bool:
        return not self <= other

    def __ge__(self, other: "Severity") -> bool:
        return not self < other


class Scope(str, Enum):
    FIELD = "field"
    ENTITY = "entity"
    COLLECTION = "collection"


class Category(str, Enum):
    STRUCTURAL = "structural"
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    UNIQUENESS = "uniqueness"
    REFERENTIAL = "referential"
    BUSINESS = "business"


class Disposition(str, Enum):
    PUBLISHABLE = "publishable"
    BLOCKED = "blocked"
    HELD = "held"


class ActionType(str, Enum):
    PUBLISH = "publish"
    RAISE_EXCEPTION = "raise_exception"
    HOLD = "hold"
    DROP = "drop"
