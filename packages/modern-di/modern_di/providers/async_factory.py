import enum
import typing

from modern_di.providers.abstract import AbstractCreatorProvider


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class AsyncFactory(AbstractCreatorProvider[T_co]):
    __slots__ = AbstractCreatorProvider.BASE_SLOTS

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
        **__: object,
    ) -> T_co:
        coroutine: typing.Awaitable[T_co] = self._creator(*args, **kwargs)
        return await coroutine
