"""Walk the members of a scope enum: which scopes are deeper than a given one."""

import enum


def deeper_members(scope: enum.IntEnum) -> list[enum.IntEnum]:
    """Members of ``scope``'s own enum that are deeper than it, shallowest first."""
    return sorted(member for member in type(scope) if member > scope)


# Keyed by the enum type as well as the member: `IntEnum` members hash by integer value, so
# two custom scopes reusing a value (TENANT=6 in one enum, 6 in another) would collide.
_next_deeper_memo: dict[tuple[type[enum.IntEnum], enum.IntEnum], enum.IntEnum | None] = {}


def next_deeper(scope: enum.IntEnum) -> enum.IntEnum | None:
    """Return the next deeper member, or None when ``scope`` is the deepest.

    None rather than ``MaxScopeReachedError``: ``exceptions`` imports this module.
    """
    key = (type(scope), scope)
    if key not in _next_deeper_memo:
        members = deeper_members(scope)
        _next_deeper_memo[key] = members[0] if members else None
    return _next_deeper_memo[key]
