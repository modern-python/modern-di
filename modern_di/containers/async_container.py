import contextlib
import types

from modern_di.containers import AbstractContainer


class AsyncContainer(AbstractContainer, contextlib.AbstractAsyncContextManager["AsyncContainer"]):
    __slots__ = AbstractContainer.BASE_SLOTS

    async def __aenter__(self) -> "AsyncContainer":
        self._enter()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        for resolver_state in reversed(self._factory_states.values()):
            await resolver_state.async_tear_down()
        self._exit()
