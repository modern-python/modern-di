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


def _next_deeper(scope: enum.IntEnum) -> enum.IntEnum | None:
    """Return the next deeper member, or None when ``scope`` is the deepest.

    Returns None rather than raising ``MaxScopeReachedError`` so this module stays
    dependency-free: ``exceptions`` imports it, so importing ``exceptions`` back would cycle.
    """
    members = _deeper_members(scope)
    return members[0] if members else None
