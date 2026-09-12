import enum


class Scope(enum.IntEnum):
    """The scopes a provider can be bound to, ordered shallow → deep by integer value.

    A provider resolves only from a container at the same or a deeper scope; from a shallower one
    it raises ``ScopeNotInitializedError``. These members are the defaults — the ordering rule is
    what matters, and any custom ``IntEnum`` works as a scope.
    """

    APP = 1
    SESSION = 2
    REQUEST = 3
    ACTION = 4
    STEP = 5


def _deeper_members(scope: enum.IntEnum) -> list[enum.IntEnum]:
    """Members of ``scope``'s own enum that are deeper than it, shallowest first."""
    return sorted(member for member in type(scope) if member > scope)


# Keyed by the enum type as well as the member: `IntEnum` members hash by integer value, so
# two custom scopes reusing a value (TENANT=6 in one enum, 6 in another) would collide.
_next_deeper_memo: dict[tuple[type[enum.IntEnum], enum.IntEnum], enum.IntEnum | None] = {}


def _next_deeper(scope: enum.IntEnum) -> enum.IntEnum | None:
    """Return the next deeper member, or None when ``scope`` is the deepest.

    None rather than ``MaxScopeReachedError``: ``exceptions`` imports this module.
    """
    key = (type(scope), scope)
    if key not in _next_deeper_memo:
        members = _deeper_members(scope)
        _next_deeper_memo[key] = members[0] if members else None
    return _next_deeper_memo[key]
