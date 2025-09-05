import contextlib
import threading
import types
import typing

from modern_di.containers.abstract import AbstractContainer
from modern_di.providers import ContainerProvider
from modern_di.providers.abstract import AbstractProvider


if typing.TYPE_CHECKING:
    pass


T_co = typing.TypeVar("T_co", covariant=True)


class SyncContainer(contextlib.AbstractContextManager["SyncContainer"], AbstractContainer):
    __slots__ = AbstractContainer.BASE_SLOTS
    LOCK_FACTORY = threading.Lock

    def _resolve_args(self, args: list[typing.Any]) -> list[typing.Any]:
        return [self.resolve_provider(x) if isinstance(x, AbstractProvider) else x for x in args]

    def _resolve_kwargs(self, kwargs: dict[str, typing.Any]) -> dict[str, typing.Any]:
        return {k: self.resolve_provider(v) if isinstance(v, AbstractProvider) else v for k, v in kwargs.items()}

    def resolve_provider(self, provider: AbstractProvider[T_co]) -> T_co:
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

        if provider_state and provider_state.lock:
            provider_state.lock.acquire()
        try:
            if provider_state and provider_state.instance is not None:
                return provider_state.instance

            return provider.sync_resolve(
                args=self._resolve_args(provider.fetch_args(self.context)),
                kwargs=self._resolve_kwargs(provider.fetch_kwargs(self.context)),
                context=self.context,
                provider_state=provider_state,
            )
        finally:
            if provider_state and provider_state.lock:
                provider_state.lock.release()

    def enter(self) -> "SyncContainer":
        self._is_entered = True
        return self

    def close(self) -> None:
        self._check_entered()
        for provider_state in reversed(self._provider_states.values()):
            provider_state.sync_tear_down()
        self._clear_state()

    def __enter__(self) -> "SyncContainer":
        return self.enter()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        self.close()
