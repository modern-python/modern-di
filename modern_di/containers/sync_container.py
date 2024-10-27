import contextlib
import types

from modern_di.containers import AbstractContainer


class SyncContainer(AbstractContainer, contextlib.AbstractContextManager["SyncContainer"]):
    __slots__ = AbstractContainer.BASE_SLOTS

    def __enter__(self) -> "SyncContainer":
        self._enter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        for resolver_state in reversed(self._factory_states.values()):
            resolver_state.sync_tear_down()
        self._exit()
