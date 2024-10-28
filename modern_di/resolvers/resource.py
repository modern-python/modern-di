import contextlib
import enum
import inspect
import typing

from modern_di import Container
from modern_di.resolvers import AbstractResolver, BaseCreatorResolver


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
        super().__init__(scope, *args, **kwargs)
        self._creator: typing.Any
        if inspect.isasyncgenfunction(creator):
            self._is_async = True
            self._creator = contextlib.asynccontextmanager(creator)
        elif inspect.isgeneratorfunction(creator):
            self._is_async = False
            self._creator = contextlib.contextmanager(creator)
        else:
            msg = "Unsupported resource type"
            raise RuntimeError(msg)

    async def async_resolve(self, container: Container) -> T_co:
        if self._override:
            return typing.cast(T_co, self._override)

        container = container.find_container(self.scope)
        factory_state = container.fetch_resolver_state(self.resolver_id, is_async=True, is_resource=True)
        if factory_state.instance:
            return typing.cast(T_co, factory_state.instance)

        if factory_state.resolver_lock:
            await factory_state.resolver_lock.acquire()

        try:
            if factory_state.instance:
                return typing.cast(T_co, factory_state.instance)

            _intermediate_ = self._creator(
                *typing.cast(
                    P.args,
                    [await x.async_resolve(container) if isinstance(x, AbstractResolver) else x for x in self._args],
                ),
                **typing.cast(
                    P.kwargs,
                    {
                        k: await v.async_resolve(container) if isinstance(v, AbstractResolver) else v
                        for k, v in self._kwargs.items()
                    },
                ),
            )

            if self._is_creator_async(self._creator):
                factory_state.context_stack = contextlib.AsyncExitStack()
                factory_state.instance = await factory_state.context_stack.enter_async_context(_intermediate_)
            else:
                factory_state.context_stack = contextlib.ExitStack()
                factory_state.instance = factory_state.context_stack.enter_context(_intermediate_)
        finally:
            if factory_state.resolver_lock:
                factory_state.resolver_lock.release()

        return typing.cast(T_co, factory_state.instance)

    def sync_resolve(self, container: Container) -> T_co:
        if self._override:
            return typing.cast(T_co, self._override)

        container = container.find_container(self.scope)
        factory_state = container.fetch_resolver_state(self.resolver_id, is_async=False, is_resource=True)
        if factory_state.instance:
            return typing.cast(T_co, factory_state.instance)

        if self._is_async:
            msg = "Async resource cannot be resolved synchronously"
            raise RuntimeError(msg)

        _intermediate_ = self._creator(
            *typing.cast(
                P.args, [x.sync_resolve(container) if isinstance(x, AbstractResolver) else x for x in self._args]
            ),
            **typing.cast(
                P.kwargs,
                {
                    k: v.sync_resolve(container) if isinstance(v, AbstractResolver) else v
                    for k, v in self._kwargs.items()
                },
            ),
        )

        factory_state.context_stack = contextlib.ExitStack()
        factory_state.instance = factory_state.context_stack.enter_context(
            typing.cast(contextlib.AbstractContextManager[typing.Any], _intermediate_)
        )

        return typing.cast(T_co, factory_state.instance)
