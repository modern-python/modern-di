import asyncio
import contextlib
import typing


T_co = typing.TypeVar("T_co", covariant=True)


class ProviderState(typing.Generic[T_co]):
    __slots__ = "context_stack", "instance", "provider_lock"

    def __init__(self, is_lock_required: bool) -> None:
        self.context_stack: contextlib.AsyncExitStack | contextlib.ExitStack | None = None
        self.instance: T_co | None = None
        self.provider_lock: typing.Final = asyncio.Lock() if is_lock_required else None

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
