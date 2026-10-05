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
