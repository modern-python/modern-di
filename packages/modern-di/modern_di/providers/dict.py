import enum
import typing

from modern_di import Container
from modern_di.providers.abstract import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)


class Dict(AbstractProvider[dict[str, T_co]]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_providers"]

    def __init__(self, scope: enum.IntEnum, **providers: AbstractProvider[T_co]) -> None:
        super().__init__(scope)
        self._check_providers_scope(providers.values())
        self._providers: typing.Final = providers

    async def async_resolve(self, container: Container) -> dict[str, T_co]:
        return {key: await provider.async_resolve(container) for key, provider in self._providers.items()}

    def sync_resolve(self, container: Container) -> dict[str, T_co]:
        return {key: provider.sync_resolve(container) for key, provider in self._providers.items()}
