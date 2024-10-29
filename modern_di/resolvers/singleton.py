import enum
import typing

from modern_di import Container
from modern_di.resolvers import BaseCreatorResolver


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class Singleton(BaseCreatorResolver[T_co]):
    __slots__ = [*BaseCreatorResolver.BASE_SLOTS, "_creator"]

    def __init__(
        self,
        scope: enum.IntEnum,
        creator: typing.Callable[P, T_co],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        super().__init__(scope, creator, *args, **kwargs)

    async def async_resolve(self, container: Container) -> T_co:
        container = container.find_container(self.scope)
        if (override := container.fetch_override(self.resolver_id)) is not None:
            return typing.cast(T_co, override)

        resolver_state = container.fetch_resolver_state(self.resolver_id)
        if resolver_state.instance is not None:
            return typing.cast(T_co, resolver_state.instance)

        resolver_state.instance = typing.cast(T_co, await self._async_build_creator(container))
        return resolver_state.instance

    def sync_resolve(self, container: Container) -> T_co:
        container = container.find_container(self.scope)
        if (override := container.fetch_override(self.resolver_id)) is not None:
            return typing.cast(T_co, override)

        resolver_state = container.fetch_resolver_state(self.resolver_id)
        if resolver_state.instance is not None:
            return typing.cast(T_co, resolver_state.instance)

        resolver_state.instance = self._sync_build_creator(container)
        return typing.cast(T_co, resolver_state.instance)
