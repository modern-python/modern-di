import typing

from modern_di import types
from modern_di.providers import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


class ContextProvider(AbstractProvider[types.T_co]):
    __slots__ = AbstractProvider.BASE_SLOTS

    def __init__(self, *, scope: Scope = Scope.APP, context_type: type[types.T_co]) -> None:
        super().__init__(scope=scope, bound_type=context_type)

    def validate(self, _: "Container") -> dict[str, typing.Any]:
        return {"bound_type": self.bound_type, "self": self}

    def resolve(self, container: "Container") -> types.T_co | None:
        container = container.find_container(self.scope)
        return container.context_registry.find_context(typing.cast(type[types.T_co], self.bound_type))
