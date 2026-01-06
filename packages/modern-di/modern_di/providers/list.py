import typing

from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


T_co = typing.TypeVar("T_co", covariant=True)


class List(AbstractProvider[list[T_co]]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "providers"]

    def __init__(self, *providers: AbstractProvider[T_co], scope: Scope = Scope.APP) -> None:
        super().__init__(scope=scope, bound_type=None)
        self.providers = list(providers)

    def resolve(self, container: "Container") -> list[T_co]:
        return [container.resolve_provider(x) for x in self.providers]
