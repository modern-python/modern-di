import enum
import typing

from modern_di import Container
from modern_di.providers.abstract import AbstractCreatorProvider


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class AsyncSingleton(AbstractCreatorProvider[T_co]):
    __slots__ = AbstractCreatorProvider.BASE_SLOTS

    def __init__(
        self,
        scope: enum.IntEnum,
        creator: typing.Callable[P, typing.Awaitable[T_co]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        super().__init__(scope, creator, *args, **kwargs)

    async def async_resolve(self, container: Container) -> T_co:
        container = container.find_container(self.scope)
        if (override := container.fetch_override(self.provider_id)) is not None:
            return typing.cast(T_co, override)

        provider_state = container.fetch_provider_state(self.provider_id, use_asyncio_lock=True)
        if provider_state.instance is not None:
            return typing.cast(T_co, provider_state.instance)

        assert provider_state.asyncio_lock
        await provider_state.asyncio_lock.acquire()

        try:
            if provider_state.instance is not None:
                return typing.cast(T_co, provider_state.instance)

            coroutine: typing.Awaitable[T_co] = await self._async_build_creator(container)
            provider_state.instance = await coroutine
        finally:
            provider_state.asyncio_lock.release()

        return provider_state.instance

    def sync_resolve(self, _: Container) -> typing.NoReturn:
        msg = "AsyncSingleton cannot be resolved synchronously"
        raise RuntimeError(msg)
