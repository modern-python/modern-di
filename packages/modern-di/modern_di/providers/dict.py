import enum
import typing

from modern_di.providers.abstract import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)


class Dict(AbstractProvider[dict[str, T_co]]):
    __slots__ = AbstractProvider.BASE_SLOTS

    def __init__(self, scope: enum.IntEnum, **kwargs: AbstractProvider[T_co]) -> None:
        super().__init__(scope, kwargs=kwargs)

    async def async_resolve(
        self,
        *,
        kwargs: dict[str, typing.Any] | None,
        **__: object,
    ) -> dict[str, T_co]:
        return kwargs or {}

    def sync_resolve(
        self,
        *,
        kwargs: dict[str, typing.Any] | None,
        **__: object,
    ) -> dict[str, T_co]:
        return kwargs or {}
