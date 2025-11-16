import enum
import typing

from modern_di.providers.abstract import AbstractCreatorProvider
from modern_di.registries.state_registry.state import ProviderState


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class AsyncSingleton(AbstractCreatorProvider[T_co]):
    __slots__ = AbstractCreatorProvider.BASE_SLOTS
    HAS_STATE = True

    def __init__(
        self,
        scope: enum.IntEnum,
        creator: typing.Callable[P, typing.Awaitable[T_co]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        super().__init__(scope, creator, *args, **kwargs)
        self.is_async = True

    async def async_resolve(
        self,
        *,
        args: list[typing.Any],
        kwargs: dict[str, typing.Any],
        provider_state: ProviderState[T_co] | None,
        **__: object,
    ) -> T_co:
        assert provider_state
        coroutine: typing.Awaitable[T_co] = self._creator(*args, **kwargs)
        provider_state.instance = await coroutine
        return provider_state.instance
