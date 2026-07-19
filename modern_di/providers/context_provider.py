import enum
import typing

from modern_di import exceptions, types
from modern_di.providers.abstract import AbstractProvider


if typing.TYPE_CHECKING:
    from modern_di import Container


class ContextProvider(AbstractProvider[types.T_co]):
    """Provider for a runtime value supplied at container-build time.

    The value is passed via ``build_child_container(context={SomeType: value})``
    and looked up from the context registry at this provider's bound scope.
    Resolving it directly when no value is set raises ``ContextValueNotSetError``;
    injecting it into a non-nullable, no-default ``Factory`` parameter instead
    raises ``ArgumentResolutionError``.
    """

    __slots__ = ("context_type",)

    def __init__(
        self,
        context_type: type[types.T_co],
        *,
        scope: enum.IntEnum | types.UnsetType = types.UNSET,
        bound_type: type | None | types.UnsetType = types.UNSET,
    ) -> None:
        super().__init__(
            scope=scope, bound_type=context_type if isinstance(bound_type, types.UnsetType) else bound_type
        )
        self.context_type = context_type

    def __repr__(self) -> str:
        return f"ContextProvider(context_type={self.context_type!r}, scope={self.scope!r})"

    def resolve(self, container: "Container") -> types.T_co:
        value = self.fetch_context_value(container)
        if value is types.UNSET:
            resolving = container.find_container(self.scope)
            raise exceptions.ContextValueNotSetError(context_type=self.context_type, scope_name=resolving.scope.name)
        return typing.cast(types.T_co, value)

    def fetch_context_value(self, container: "Container") -> types.T_co | object:
        container = container.find_container(self.scope)
        container._raise_if_closed()  # noqa: SLF001
        return container.context_registry.find_context(self.context_type)
