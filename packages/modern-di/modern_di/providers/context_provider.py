import typing

from modern_di.providers import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class ContextProvider(AbstractProvider[T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "context_type"]

    def __init__(self, *, scope: Scope = Scope.APP, context_type: type[T_co]) -> None:
        super().__init__(scope=scope, bound_type=context_type)
        self.context_type = context_type

    def resolve(self, container: "Container") -> T_co | None:
        return container.context_registry.find_context(self.context_type)
