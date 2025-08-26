import enum
import typing

from modern_di.providers import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class ContainerProvider(AbstractProvider[typing.Any]):
    __slots__ = AbstractProvider.BASE_SLOTS

    def __init__(self, scope: enum.IntEnum) -> None:
        super().__init__(scope)
