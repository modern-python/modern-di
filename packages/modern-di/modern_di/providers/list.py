import enum
import typing

from modern_di import Container
from modern_di.providers.abstract import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)


class List(AbstractProvider[list[T_co]]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_providers"]

    def __init__(self, scope: enum.IntEnum, *providers: AbstractProvider[T_co]) -> None:
        super().__init__(scope)
        self._check_providers_scope(providers)
        self._providers: typing.Final = providers

    async def async_resolve(self, container: Container) -> list[T_co]:
        return [await x.async_resolve(container) for x in self._providers]

    def sync_resolve(self, container: Container) -> list[T_co]:
        return [x.sync_resolve(container) for x in self._providers]
