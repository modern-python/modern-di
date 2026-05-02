import enum
import typing

from modern_di import types
from modern_di.providers import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


class ContextProvider(AbstractProvider[types.T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_context_type"]

    def __init__(
        self,
        *,
        scope: enum.IntEnum = Scope.APP,
        context_type: type[types.T_co],
        bound_type: type | None = types.UNSET,  # ty: ignore[invalid-parameter-default]
    ) -> None:
        super().__init__(scope=scope, bound_type=bound_type if bound_type != types.UNSET else context_type)
        self._context_type = context_type

    def __repr__(self) -> str:
        return f"ContextProvider(context_type={self._context_type!r}, scope={self.scope!r})"

    def resolve(self, container: "Container") -> types.T_co | None:
        container = container.find_container(self.scope)
        return container.context_registry.find_context(self._context_type)
