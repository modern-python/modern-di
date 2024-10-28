import enum
import typing

from modern_di import Container
from modern_di.resolvers import AbstractResolver, BaseCreatorResolver


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class Factory(BaseCreatorResolver[T_co]):
    __slots__ = [*BaseCreatorResolver.BASE_SLOTS, "_creator"]

    def __init__(
        self,
        scope: enum.IntEnum,
        creator: typing.Callable[P, T_co],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        super().__init__(scope, *args, **kwargs)
        self._creator = creator

    async def async_resolve(self, container: Container) -> T_co:
        if self._override:
            return typing.cast(T_co, self._override)

        container = container.find_container(self.scope)
        factory_state = container.fetch_resolver_state(self.resolver_id, is_async=True, is_resource=False)
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

    def sync_resolve(self, container: Container) -> T_co:
        if self._override:
            return typing.cast(T_co, self._override)

        container = container.find_container(self.scope)
        factory_state = container.fetch_resolver_state(self.resolver_id, is_async=False, is_resource=False)
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
