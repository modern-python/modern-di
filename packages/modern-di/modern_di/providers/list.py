import typing

from modern_di import types
from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


class List(AbstractProvider[list[types.T_co]]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_providers"]

    def __init__(self, *providers: AbstractProvider[types.T_co], scope: Scope = Scope.APP) -> None:
        super().__init__(scope=scope, bound_type=None)
        self._providers = list(providers)

    def resolve(self, container: "Container") -> list[types.T_co]:
        return [x.resolve(container) for x in self._providers]
