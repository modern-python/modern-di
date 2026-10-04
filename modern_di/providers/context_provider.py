import enum

from modern_di import types
from modern_di.providers.abstract import AbstractProvider


class ContextProvider(AbstractProvider[types.T_co]):
    """Provider for a runtime value passed as ``build_child_container(context={SomeType: value})``.

    The value is read from the context registry at this provider's scope. With none set it resolves
    to ``default``, or raises ``ContextValueNotSetError`` when no ``default`` was given, whether
    resolved directly or as a ``Factory`` argument.
    """

    __slots__ = ("context_type", "default")

    def __init__(
        self,
        context_type: type[types.T_co],
        *,
        scope: enum.IntEnum | types.UnsetType = types.UNSET,
        bound_type: type | types.UnsetType | None = types.UNSET,
        default: "types.T_co | types.UnsetType | None" = types.UNSET,
    ) -> None:
        super().__init__(
            scope=scope, bound_type=context_type if isinstance(bound_type, types.UnsetType) else bound_type
        )
        self.context_type = context_type
        self.default = default

    def __repr__(self) -> str:
        return f"ContextProvider(context_type={self.context_type!r}, scope={self.scope!r})"
