import enum
import typing

from modern_di.providers.abstract import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class Object(AbstractProvider[T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_obj"]

    def __init__(self, scope: enum.IntEnum, obj: T_co) -> None:
        super().__init__(scope)
        self._obj: typing.Final = obj

    async def async_resolve(self, *_: object, **__: object) -> T_co:
        return self._obj

    def sync_resolve(self, *_: object, **__: object) -> T_co:
        return self._obj
