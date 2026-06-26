import enum
import typing

from modern_di import exceptions, types
from modern_di.providers import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


class ContextProvider(AbstractProvider[types.T_co]):
    """Provider for a runtime value supplied at container-build time.

    The value is passed via ``build_child_container(context={SomeType: value})``
    and looked up from the context registry at this provider's bound scope.
    Resolving it directly when no value is set returns ``None``; injecting it into
    a non-nullable, no-default ``Factory`` parameter instead raises
    ``ArgumentResolutionError``.
    """

    __slots__ = ("context_type",)

    def __init__(
        self,
        *,
        scope: enum.IntEnum = Scope.APP,
        context_type: type[types.T_co],
        bound_type: type | None | types.UnsetType = types.UNSET,
    ) -> None:
        super().__init__(
            scope=scope, bound_type=context_type if isinstance(bound_type, types.UnsetType) else bound_type
        )
        # Public, like its sibling ``bound_type`` — the type this provider supplies and
        # the key its value is set under in ``context``.
        self.context_type = context_type

    def __repr__(self) -> str:
        return f"ContextProvider(context_type={self.context_type!r}, scope={self.scope!r})"

    def resolve(self, container: "Container") -> types.T_co | None:
        value = self.fetch_context_value(container)
        if value is types.UNSET:
            return None
        return typing.cast(types.T_co, value)

    def fetch_context_value(self, container: "Container") -> types.T_co | object:
        container = container.find_container(self.scope)
        if container.closed:
            raise exceptions.ContainerClosedError(container_scope=container.scope)
        return container.context_registry.find_context(self.context_type)
