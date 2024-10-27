import enum
import itertools
import typing

from modern_di.containers import AsyncContainer, SyncContainer
from modern_di.resolvers import AbstractResolver


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class Factory(AbstractResolver[T_co]):
    __slots__ = [*AbstractResolver.BASE_SLOTS, "_creator", "_args", "_kwargs"]

    def __init__(
        self,
        scope: enum.IntEnum,
        creator: typing.Callable[P, T_co],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        super().__init__(scope)

        if any(x.scope > self.scope for x in itertools.chain(args, kwargs.values()) if isinstance(x, AbstractResolver)):
            msg = "Scope of dependency cannot be more than scope of dependent"
            raise RuntimeError(msg)

        self._creator = creator
        self._args: typing.Final = args
        self._kwargs: typing.Final = kwargs

    async def async_resolve(self, container: AsyncContainer) -> T_co:
        if self._override:
            return typing.cast(T_co, self._override)

        container = container.find_container(self.scope)
        factory_state = container.fetch_resolver_state(self.resolver_id, is_async=True)
        if factory_state.instance:
            return typing.cast(T_co, factory_state.instance)

        if factory_state.resolver_lock:
            await factory_state.resolver_lock.acquire()

        try:
            if factory_state.instance:
                return typing.cast(T_co, factory_state.instance)

            factory_state.instance = self._creator(
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
        finally:
            if factory_state.resolver_lock:
                factory_state.resolver_lock.release()

        return factory_state.instance

    def sync_resolve(self, container: SyncContainer) -> T_co:
        if self._override:
            return typing.cast(T_co, self._override)

        container = container.find_container(self.scope)
        factory_state = container.fetch_resolver_state(self.resolver_id, is_async=False)
        if factory_state.instance:
            return typing.cast(T_co, factory_state.instance)

        factory_state.instance = self._creator(
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
        return factory_state.instance
