import contextlib
import types
import typing

from modern_di.containers.abstract import AbstractContainer
from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.container_provider import ContainerProvider
from modern_di.providers.context_provider import ContextProvider


if typing.TYPE_CHECKING:
    pass


T_co = typing.TypeVar("T_co", covariant=True)


class AsyncContainer(contextlib.AbstractAsyncContextManager["AsyncContainer"], AbstractContainer):
    __slots__ = AbstractContainer.BASE_SLOTS

    async def _resolve_args(self, args: list[typing.Any]) -> list[typing.Any]:
        return [await self.resolve_provider(x) if isinstance(x, AbstractProvider) else x for x in args]

    async def _resolve_kwargs(self, kwargs: dict[str, typing.Any]) -> dict[str, typing.Any]:
        return {k: await self.resolve_provider(v) if isinstance(v, AbstractProvider) else v for k, v in kwargs.items()}

    async def resolve(self, dependency_type: type[T_co] | None = None, *, dependency_name: str | None = None) -> T_co:
        provider = self.providers_registry.find_provider(
            dependency_type=dependency_type, dependency_name=dependency_name
        )
        if not provider:
            msg = f"Provider is not found, {dependency_type=}, {dependency_name=}"
            raise RuntimeError(msg)

        return await self.resolve_provider(provider)

    async def resolve_provider(self, provider: AbstractProvider[T_co]) -> T_co:
        self._check_entered()

        container = self.find_container(provider.scope)
        if isinstance(provider, ContainerProvider):
            return typing.cast(T_co, container)

        if isinstance(provider, ContextProvider):
            return typing.cast(T_co, self._resolve_context_provider(provider))

        if (override := container.overrides_registry.fetch_override(provider.provider_id)) is not None:
            return typing.cast(T_co, override)

        provider_state = container.state_registry.fetch_provider_state(provider)
        if provider_state and provider_state.instance is not None:
            return provider_state.instance

        args = await self._resolve_args(provider.args or [])
        kwargs = await self._resolve_kwargs(provider.kwargs or {})

        if provider_state and self._async_lock:
            await self._async_lock.acquire()
        try:
            if provider_state and provider_state.instance is not None:
                return provider_state.instance

            return await provider.async_resolve(
                args=args,
                kwargs=kwargs,
                provider_state=provider_state,
            )
        finally:
            if provider_state and self._async_lock:
                self._async_lock.release()

    def sync_resolve(self, dependency_type: type[T_co] | None = None, *, dependency_name: str | None = None) -> T_co:
        return self._sync_resolve(dependency_type=dependency_type, dependency_name=dependency_name)

    def sync_resolve_provider(self, provider: AbstractProvider[T_co]) -> T_co:
        return self._sync_resolve_provider(provider)

    def enter(self) -> "AsyncContainer":
        self._is_entered = True
        return self

    async def close(self) -> None:
        self._check_entered()
        self._is_entered = False
        await self.state_registry.async_tear_down()
        self.overrides_registry.reset_override()

    async def __aenter__(self) -> "AsyncContainer":
        return self.enter()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        await self.close()
