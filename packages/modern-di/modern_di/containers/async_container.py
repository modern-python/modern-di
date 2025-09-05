import asyncio
import contextlib
import types
import typing

from modern_di.containers.abstract import AbstractContainer
from modern_di.providers import ContainerProvider
from modern_di.providers.abstract import AbstractProvider


if typing.TYPE_CHECKING:
    pass


T_co = typing.TypeVar("T_co", covariant=True)


class AsyncContainer(contextlib.AbstractAsyncContextManager["AsyncContainer"], AbstractContainer):
    __slots__ = AbstractContainer.BASE_SLOTS
    LOCK_FACTORY = asyncio.Lock

    async def _resolve_args(self, args: list[typing.Any]) -> list[typing.Any]:
        return [await self.resolve_provider(x) if isinstance(x, AbstractProvider) else x for x in args]

    async def _resolve_kwargs(self, kwargs: dict[str, typing.Any]) -> dict[str, typing.Any]:
        return {k: await self.resolve_provider(v) if isinstance(v, AbstractProvider) else v for k, v in kwargs.items()}

    async def resolve_provider(self, provider: AbstractProvider[T_co]) -> T_co:
        self._check_entered()

        container = self.find_container(provider.scope)
        if isinstance(provider, ContainerProvider):
            return typing.cast(T_co, container)

        if (override := container.overrides_registry.fetch_override(provider.provider_id)) is not None:
            return typing.cast(T_co, override)

        provider_state = container.fetch_provider_state(provider)
        if provider_state and provider_state.instance is not None:
            return provider_state.instance

        if provider_state and provider_state.lock:
            await provider_state.lock.acquire()
        try:
            if provider_state and provider_state.instance is not None:
                return provider_state.instance

            return await provider.async_resolve(
                args=await self._resolve_args(provider.fetch_args(self.context)),
                kwargs=await self._resolve_kwargs(provider.fetch_kwargs(self.context)),
                context=self.context,
                provider_state=provider_state,
            )
        finally:
            if provider_state and provider_state.lock:
                provider_state.lock.release()

    def enter(self) -> "AsyncContainer":
        self._is_entered = True
        return self

    async def close(self) -> None:
        self._check_entered()
        for provider_state in reversed(self._provider_states.values()):
            await provider_state.async_tear_down()
        self._clear_state()

    async def __aenter__(self) -> "AsyncContainer":
        return self.enter()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        await self.close()
