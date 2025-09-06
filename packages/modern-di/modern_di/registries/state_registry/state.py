import asyncio
import contextlib
import threading
import typing


T_co = typing.TypeVar("T_co", covariant=True)


class AsyncState(typing.Generic[T_co]):
    __slots__ = "context_stack", "instance", "lock", "use_lock"

    def __init__(self, use_lock: bool = True) -> None:
        self.lock: typing.Final = asyncio.Lock() if use_lock else None
        self.context_stack: contextlib.AsyncExitStack | contextlib.ExitStack | None = None
        self.instance: T_co | None = None

    async def tear_down(self) -> None:
        if self.context_stack is None:
            return

        if isinstance(self.context_stack, contextlib.AsyncExitStack):
            await self.context_stack.aclose()
        else:
            self.context_stack.close()
        self.context_stack = None
        self.instance = None


class SyncState(typing.Generic[T_co]):
    __slots__ = "context_stack", "instance", "lock", "use_lock"

    def __init__(self, use_lock: bool = True) -> None:
        self.lock: typing.Final = threading.Lock() if use_lock else None
        self.context_stack: contextlib.ExitStack | None = None
        self.instance: T_co | None = None

    def tear_down(self) -> None:
        if self.context_stack is None:
            return

        self.context_stack.close()
        self.context_stack = None
        self.instance = None
