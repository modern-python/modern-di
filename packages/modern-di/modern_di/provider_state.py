import contextlib
import typing


T_co = typing.TypeVar("T_co", covariant=True)


class ProviderState(typing.Generic[T_co]):
    __slots__ = "context_stack", "instance", "lock"

    def __init__(self, lock_factory: type[typing.Any]) -> None:
        self.context_stack: contextlib.AsyncExitStack | contextlib.ExitStack | None = None
        self.instance: T_co | None = None
        self.lock: typing.Final = lock_factory()

    async def async_tear_down(self) -> None:
        if self.context_stack is None:
            return

        if isinstance(self.context_stack, contextlib.AsyncExitStack):
            await self.context_stack.aclose()
        else:
            self.context_stack.close()
        self.context_stack = None
        self.instance = None

    def sync_tear_down(self) -> None:
        if self.context_stack is None:
            return

        if isinstance(self.context_stack, contextlib.AsyncExitStack):
            msg = "Cannot tear down async context in `sync_tear_down`"
            raise RuntimeError(msg)  # noqa: TRY004

        self.context_stack.close()
        self.context_stack = None
        self.instance = None
