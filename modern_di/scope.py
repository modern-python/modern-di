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
