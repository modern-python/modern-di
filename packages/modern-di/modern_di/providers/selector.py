import enum
import typing

from modern_di.providers.abstract import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class Selector(AbstractProvider[T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_function"]

    def __init__(
        self, scope: enum.IntEnum, function: typing.Callable[..., str], **providers: AbstractProvider[T_co]
    ) -> None:
        super().__init__(scope, kwargs=providers)
        self._function: typing.Final = function

    def fetch_kwargs(self, context: dict[str, typing.Any]) -> dict[str, typing.Any]:
        selected_key = self._function(**context)
        if self._kwargs and (provider := self._kwargs.get(selected_key)):
            return {selected_key: provider}

        msg = f"No provider matches {selected_key}"
        raise RuntimeError(msg)

    async def async_resolve(
        self,
        *,
        kwargs: dict[str, typing.Any],
        **_: object,
    ) -> T_co:
        return typing.cast(T_co, next(iter(kwargs.values())))

    def sync_resolve(
        self,
        *,
        kwargs: dict[str, typing.Any],
        **_: object,
    ) -> T_co:
        return typing.cast(T_co, next(iter(kwargs.values())))
