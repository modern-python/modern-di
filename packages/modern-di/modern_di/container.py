import contextlib
import enum
import types
import typing

from modern_di.provider_state import ProviderState
from modern_di.providers import ContainerProvider
from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    import typing_extensions


T_co = typing.TypeVar("T_co", covariant=True)


class Container(contextlib.AbstractAsyncContextManager["Container"], contextlib.AbstractContextManager["Container"]):
    __slots__ = (
        "_is_async",
        "_overrides",
        "_provider_states",
        "_use_threading_lock",
        "context",
        "parent_container",
        "scope",
    )

    def __init__(
        self,
        *,
        scope: enum.IntEnum = Scope.APP,
        parent_container: typing.Optional["Container"] = None,
        context: dict[str, typing.Any] | None = None,
        use_threading_lock: bool = True,
    ) -> None:
        self.scope = scope
        self.parent_container = parent_container
        self.context: dict[str, typing.Any] = context or {}
        self._is_async: bool | None = None
        self._provider_states: dict[str, ProviderState[typing.Any]] = {}
        self._overrides: dict[str, typing.Any] = parent_container._overrides if parent_container else {}  # noqa: SLF001
        self._use_threading_lock = use_threading_lock

    def _exit(self) -> None:
        self._is_async = None
        self._provider_states = {}
        self._overrides = {}
        self.context = {}

    def _check_entered(self) -> None:
        if self._is_async is None:
            msg = f"Enter the context of {self.scope.name} scope"
            raise RuntimeError(msg)

    def build_child_container(
        self, context: dict[str, typing.Any] | None = None, scope: enum.IntEnum | None = None
    ) -> "typing_extensions.Self":
        self._check_entered()
        if scope and scope <= self.scope:
            msg = "Scope of child container must be more than current scope"
            raise RuntimeError(msg)

        if not scope:
            try:
                scope = self.scope.__class__(self.scope.value + 1)
            except ValueError as exc:
                msg = f"Max scope is reached, {self.scope.name}"
                raise RuntimeError(msg) from exc

        return self.__class__(scope=scope, parent_container=self, context=context)

    def find_container(self, scope: enum.IntEnum) -> "typing_extensions.Self":
        container = self
        if container.scope < scope:
            msg = f"Scope {scope.name} is not initialized"
            raise RuntimeError(msg)

        while container.scope > scope and container.parent_container:
            container = typing.cast("typing_extensions.Self", container.parent_container)

        if container.scope != scope:
            msg = f"Scope {scope.name} is skipped"
            raise RuntimeError(msg)

        return container

    def fetch_provider_state(self, provider: AbstractProvider[T_co]) -> ProviderState[T_co] | None:
        if not provider.HAS_STATE:
            return None

        if provider_state := self._provider_states.get(provider.provider_id):
            return provider_state

        # expected to be thread-safe, because setdefault is atomic
        return self._provider_states.setdefault(
            provider.provider_id,
            ProviderState(
                use_asyncio_lock=self._is_async or False,
                use_threading_lock=self._use_threading_lock,
            ),
        )

    def override(self, provider: AbstractProvider[T_co], override_object: object) -> None:
        self._overrides[provider.provider_id] = override_object

    def reset_override(self, provider: AbstractProvider[T_co] | None = None) -> None:
        if provider is None:
            self._overrides = {}
        else:
            self._overrides.pop(provider.provider_id, None)

    def fetch_override(self, provider_id: str) -> object | None:
        return self._overrides.get(provider_id)

    def _sync_resolve_args(self, args: list[typing.Any]) -> list[typing.Any]:
        return [self.sync_resolve_provider(x) if isinstance(x, AbstractProvider) else x for x in args]

    def _sync_resolve_kwargs(self, kwargs: dict[str, typing.Any]) -> dict[str, typing.Any]:
        return {k: self.sync_resolve_provider(v) if isinstance(v, AbstractProvider) else v for k, v in kwargs.items()}

    async def _async_resolve_args(self, args: list[typing.Any]) -> list[typing.Any]:
        return [await self.async_resolve_provider(x) if isinstance(x, AbstractProvider) else x for x in args]

    async def _async_resolve_kwargs(self, kwargs: dict[str, typing.Any]) -> dict[str, typing.Any]:
        return {
            k: await self.async_resolve_provider(v) if isinstance(v, AbstractProvider) else v for k, v in kwargs.items()
        }

    def sync_resolve_provider(self, provider: AbstractProvider[T_co]) -> T_co:
        self._check_entered()
        if provider.is_async:
            msg = f"{type(provider).__name__} cannot be resolved synchronously"
            raise RuntimeError(msg)

        container = self.find_container(provider.scope)
        if isinstance(provider, ContainerProvider):
            return typing.cast(T_co, container)

        if (override := container.fetch_override(provider.provider_id)) is not None:
            return typing.cast(T_co, override)

        provider_state = container.fetch_provider_state(provider)
        if provider_state and provider_state.instance is not None:
            return provider_state.instance

        if provider_state and provider_state.threading_lock:
            provider_state.threading_lock.acquire()
        try:
            if provider_state and provider_state.instance is not None:
                return provider_state.instance

            return provider.sync_resolve(
                args=self._sync_resolve_args(provider.fetch_args(self.context)),
                kwargs=self._sync_resolve_kwargs(provider.fetch_kwargs(self.context)),
                context=self.context,
                provider_state=provider_state,
            )
        finally:
            if provider_state and provider_state.threading_lock:
                provider_state.threading_lock.release()

    async def async_resolve_provider(self, provider: AbstractProvider[T_co]) -> T_co:
        self._check_entered()
        if provider.is_async and not self._is_async:
            msg = "Async resolving is forbidden in sync container"
            raise RuntimeError(msg)

        container = self.find_container(provider.scope)
        if isinstance(provider, ContainerProvider):
            return typing.cast(T_co, container)

        if (override := container.fetch_override(provider.provider_id)) is not None:
            return typing.cast(T_co, override)

        provider_state = container.fetch_provider_state(provider)
        if provider_state and provider_state.instance is not None:
            return provider_state.instance

        if provider_state and provider_state.asyncio_lock:
            await provider_state.asyncio_lock.acquire()
        try:
            if provider_state and provider_state.instance is not None:
                return provider_state.instance

            return await provider.async_resolve(
                args=await self._async_resolve_args(provider.fetch_args(self.context)),
                kwargs=await self._async_resolve_kwargs(provider.fetch_kwargs(self.context)),
                context=self.context,
                provider_state=provider_state,
            )
        finally:
            if provider_state and provider_state.asyncio_lock:
                provider_state.asyncio_lock.release()

    def async_enter(self) -> "Container":
        self._is_async = True
        return self

    def sync_enter(self) -> "Container":
        self._is_async = False
        return self

    async def async_close(self) -> None:
        self._check_entered()
        for provider_state in reversed(self._provider_states.values()):
            await provider_state.async_tear_down()
        self._exit()

    def sync_close(self) -> None:
        self._check_entered()
        for provider_state in reversed(self._provider_states.values()):
            provider_state.sync_tear_down()
        self._exit()

    async def __aenter__(self) -> "Container":
        return self.async_enter()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        await self.async_close()

    def __enter__(self) -> "Container":
        return self.sync_enter()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        self.sync_close()

    def __deepcopy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Hack to prevent cloning object."""
        return self

    def __copy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Hack to prevent cloning object."""
        return self
