import enum
import typing

from modern_di import Container
from modern_di.providers.abstract import AbstractCreatorProvider
from modern_di.providers.injected_factory import AsyncInjectedFactory, SyncInjectedFactory


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class Factory(AbstractCreatorProvider[T_co]):
    __slots__ = [*AbstractCreatorProvider.BASE_SLOTS, "_creator"]

    def __init__(
        self,
        scope: enum.IntEnum,
        creator: typing.Callable[P, T_co],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        super().__init__(scope, creator, *args, **kwargs)

    @property
    def sync_provider(self) -> SyncInjectedFactory[T_co]:
        return SyncInjectedFactory(self)

    @property
    def async_provider(self) -> AsyncInjectedFactory[T_co]:
        return AsyncInjectedFactory(self)

    async def async_resolve(self, container: Container) -> T_co:
        container = container.find_container(self.scope)
        if (override := container.fetch_override(self.provider_id)) is not None:
            return typing.cast(T_co, override)

        return typing.cast(T_co, await self._async_build_creator(container))

    def sync_resolve(self, container: Container) -> T_co:
        container = container.find_container(self.scope)
        if (override := container.fetch_override(self.provider_id)) is not None:
            return typing.cast(T_co, override)

        return typing.cast(T_co, self._sync_build_creator(container))
