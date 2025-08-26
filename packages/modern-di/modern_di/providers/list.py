import enum
import typing

from modern_di.providers.abstract import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)


class List(AbstractProvider[list[T_co]]):
    __slots__ = AbstractProvider.BASE_SLOTS

    def __init__(self, scope: enum.IntEnum, *args: AbstractProvider[T_co]) -> None:
        super().__init__(scope, args=list(args))

    async def async_resolve(
        self,
        *,
        args: list[typing.Any] | None,
        **__: object,
    ) -> list[T_co]:
        return args or []

    def sync_resolve(
        self,
        *,
        args: list[typing.Any] | None,
        **__: object,
    ) -> list[T_co]:
        return args or []
