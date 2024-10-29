import contextlib
import enum
import inspect
import typing

from modern_di import Container
from modern_di.resolvers import BaseCreatorResolver


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class Resource(BaseCreatorResolver[T_co]):
    __slots__ = [*BaseCreatorResolver.BASE_SLOTS, "_creator", "_args", "_kwargs", "_is_async"]

    def _is_creator_async(
        self,
        _: contextlib.AbstractContextManager[T_co] | contextlib.AbstractAsyncContextManager[T_co],
    ) -> typing.TypeGuard[contextlib.AbstractAsyncContextManager[T_co]]:
        return self._is_async

    def __init__(
        self,
        scope: enum.IntEnum,
        creator: typing.Callable[P, typing.Iterator[T_co] | typing.AsyncIterator[T_co]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        new_creator: typing.Any
        if inspect.isasyncgenfunction(creator):
            self._is_async = True
            new_creator = contextlib.asynccontextmanager(creator)
        elif inspect.isgeneratorfunction(creator):
            self._is_async = False
            new_creator = contextlib.contextmanager(creator)
        else:
            msg = "Unsupported resource type"
            raise RuntimeError(msg)

        super().__init__(scope, new_creator, *args, **kwargs)

    async def async_resolve(self, container: Container) -> T_co:
        container = container.find_container(self.scope)
        if (override := container.fetch_override(self.resolver_id)) is not None:
            return typing.cast(T_co, override)

        resolver_state = container.fetch_resolver_state(
            self.resolver_id, is_async_resource=self._is_async, is_lock_required=True
        )
        if resolver_state.instance is not None:
            return typing.cast(T_co, resolver_state.instance)

        assert resolver_state.resolver_lock
        await resolver_state.resolver_lock.acquire()

        try:
            if resolver_state.instance is not None:
                return typing.cast(T_co, resolver_state.instance)

            _intermediate_ = await self._async_build_creator(container)

            if self._is_creator_async(self._creator):  # type: ignore[arg-type]
                resolver_state.context_stack = contextlib.AsyncExitStack()
                resolver_state.instance = await resolver_state.context_stack.enter_async_context(_intermediate_)
            else:
                resolver_state.context_stack = contextlib.ExitStack()
                resolver_state.instance = resolver_state.context_stack.enter_context(_intermediate_)
        finally:
            resolver_state.resolver_lock.release()

        return typing.cast(T_co, resolver_state.instance)

    def sync_resolve(self, container: Container) -> T_co:
        container = container.find_container(self.scope)
        if (override := container.fetch_override(self.resolver_id)) is not None:
            return typing.cast(T_co, override)

        resolver_state = container.fetch_resolver_state(self.resolver_id)
        if resolver_state.instance is not None:
            return typing.cast(T_co, resolver_state.instance)

        if self._is_async:
            msg = "Async resource cannot be resolved synchronously"
            raise RuntimeError(msg)

        _intermediate_ = self._sync_build_creator(container)

        resolver_state.context_stack = contextlib.ExitStack()
        resolver_state.instance = resolver_state.context_stack.enter_context(
            typing.cast(contextlib.AbstractContextManager[typing.Any], _intermediate_)
        )

        return typing.cast(T_co, resolver_state.instance)
