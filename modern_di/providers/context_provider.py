import enum
import typing

from modern_di import types
from modern_di.providers.abstract import AbstractProvider


if typing.TYPE_CHECKING:
    from modern_di import Container


class ContextProvider(AbstractProvider[types.T_co]):
    """Provider for a runtime value passed as ``build_child_container(context={SomeType: value})``.

    The value is read from the context registry at this provider's scope. Resolving it with none
    set raises ``ContextValueNotSetError``; injecting it into a non-nullable, no-default
    ``Factory`` parameter raises ``ArgumentResolutionError`` instead.
    """

    __slots__ = ("context_type",)

    def __init__(
        self,
        context_type: type[types.T_co],
        *,
        scope: enum.IntEnum | types.UnsetType = types.UNSET,
        bound_type: type | types.UnsetType | None = types.UNSET,
    ) -> None:
        super().__init__(
            scope=scope, bound_type=context_type if isinstance(bound_type, types.UnsetType) else bound_type
        )
        self.context_type = context_type

    def __repr__(self) -> str:
        return f"ContextProvider(context_type={self.context_type!r}, scope={self.scope!r})"

    def fetch_context_value(self, container: "Container") -> "types.T_co | types.UnsetType":
        """Read this provider's context value at its own scope, or UNSET when none is set."""
        if container.scope != self.scope:
            container = container.find_container(self.scope)
        if container.closed:  # guarded: `_prepare()` warns and reopens unconditionally
            container._prepare()  # noqa: SLF001
        return container.context_registry.find_context(self.context_type)
