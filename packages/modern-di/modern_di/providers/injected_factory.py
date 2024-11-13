import functools
import typing

from modern_di import Container
from modern_di.providers.abstract import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class InjectedFactory(AbstractProvider[T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_factory_provider"]

    def __init__(self, factory_provider: AbstractProvider[T_co]) -> None:
        super().__init__(factory_provider.scope)
        self._factory_provider = factory_provider

    async def async_resolve(self, container: Container) -> typing.Callable[[], T_co]:  # type: ignore[override]
        await self._factory_provider.async_resolve(container)
        return functools.partial(self._factory_provider.sync_resolve, container)

    def sync_resolve(self, container: Container) -> typing.Callable[[], T_co]:  # type: ignore[override]
        self._factory_provider.sync_resolve(container)
        return functools.partial(self._factory_provider.sync_resolve, container)

    @property
    def cast(self) -> typing.Callable[[], T_co]:  # type: ignore[override]
        return typing.cast(typing.Callable[[], T_co], self)
