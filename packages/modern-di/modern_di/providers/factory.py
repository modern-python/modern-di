import enum
import typing

from modern_di.providers.abstract import AbstractCreatorProvider


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class Factory(AbstractCreatorProvider[T_co]):
    __slots__ = AbstractCreatorProvider.BASE_SLOTS

    def __init__(
        self,
        scope: enum.IntEnum,
        creator: typing.Callable[P, T_co],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        super().__init__(scope, creator, *args, **kwargs)

    async def async_resolve(
        self,
        *,
        args: list[typing.Any],
        kwargs: dict[str, typing.Any],
        **__: object,
    ) -> T_co:
        return typing.cast(T_co, self._creator(*args, **kwargs))

    def sync_resolve(
        self,
        *,
        args: list[typing.Any],
        kwargs: dict[str, typing.Any],
        **__: object,
    ) -> T_co:
        return typing.cast(T_co, self._creator(*args, **kwargs))
