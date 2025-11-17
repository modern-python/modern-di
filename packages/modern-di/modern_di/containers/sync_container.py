import contextlib
import types
import typing

from modern_di.containers.abstract import AbstractContainer
from modern_di.providers.abstract import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)


class SyncContainer(contextlib.AbstractContextManager["SyncContainer"], AbstractContainer):
    __slots__ = AbstractContainer.BASE_SLOTS

    def resolve(self, dependency_type: type[T_co] | None = None, *, dependency_name: str | None = None) -> T_co:
        return self._sync_resolve(dependency_type=dependency_type, dependency_name=dependency_name)

    def resolve_provider(self, provider: AbstractProvider[T_co]) -> T_co:
        return self._sync_resolve_provider(provider)

    def enter(self) -> "SyncContainer":
        self._is_entered = True
        return self

    def close(self) -> None:
        self._check_entered()
        self._is_entered = False
        self.state_registry.sync_tear_down()
        self.overrides_registry.reset_override()

    def __enter__(self) -> "SyncContainer":
        return self.enter()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        self.close()
