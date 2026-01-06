import typing

from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


T_co = typing.TypeVar("T_co", covariant=True)


class Dict(AbstractProvider[dict[str, T_co]]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "providers"]

    def __init__(self, *, scope: Scope = Scope.APP, **providers: AbstractProvider[T_co]) -> None:
        super().__init__(scope=scope, bound_type=None)
        self.providers = providers

    def resolve(self, container: "Container") -> dict[str, T_co]:
        return {k: container.resolve_provider(v) for k, v in self.providers.items()}
