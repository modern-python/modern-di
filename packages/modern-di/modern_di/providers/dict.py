import typing

from modern_di import types
from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


class Dict(AbstractProvider[dict[str, types.T_co]]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_providers"]

    def __init__(self, *, scope: Scope = Scope.APP, **providers: AbstractProvider[types.T_co]) -> None:
        super().__init__(scope=scope, bound_type=None)
        self._providers = providers

    def resolve(self, container: "Container") -> dict[str, types.T_co]:
        return {k: v.resolve(container) for k, v in self._providers.items()}
