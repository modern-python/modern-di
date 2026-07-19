import enum


class Scope(enum.IntEnum):
    """Lifetime bands, ordered shallow → deep by integer value.

    A provider bound to a scope resolves only from a container at the same or a
    deeper scope (higher integer); resolving it from a shallower container raises
    ``ScopeNotInitializedError``. The members below are the defaults — the
    ordering rule is what matters, and custom ``IntEnum`` scopes are allowed.
    """

    APP = 1
    SESSION = 2
    REQUEST = 3
    ACTION = 4
    STEP = 5


def _deeper_members(scope: enum.IntEnum) -> list[enum.IntEnum]:
    """Members of ``scope``'s own enum that are deeper than it, shallowest first.

    Takes any ``IntEnum``, not just :class:`Scope`: Python forbids extending an enum that
    has members, so a custom scope is a standalone ``IntEnum`` and this rule could never
    reach it as a method.
    """
    return sorted(member for member in type(scope) if member > scope)


# Memo for `_next_deeper`: a constant function of an immutable enum member, called per child
# on the default `build_child_container()` (auto-increment) path — uncached it re-sorts the
# whole enum every time. Keyed by `(type(scope), scope)`, NOT the bare member: `IntEnum`
# members compare and hash by integer value, so two custom scopes reusing a value (TENANT=6
# in one enum, 6 in another) would collide under a plain member key; the type disambiguates.
# Bounded by the finite set of scope members ever passed. Concurrent writes are benign — the
# value is deterministic, so a race just stores the same result twice (dict setitem is atomic).
_next_deeper_memo: dict[tuple[type[enum.IntEnum], enum.IntEnum], enum.IntEnum | None] = {}


def _next_deeper(scope: enum.IntEnum) -> enum.IntEnum | None:
    """Return the next deeper member, or None when ``scope`` is the deepest.

    Returns None rather than raising ``MaxScopeReachedError`` so this module stays
    dependency-free: ``exceptions`` imports it, so importing ``exceptions`` back would cycle.
    """
    key = (type(scope), scope)
    if key not in _next_deeper_memo:
        members = _deeper_members(scope)
        _next_deeper_memo[key] = members[0] if members else None
    return _next_deeper_memo[key]
