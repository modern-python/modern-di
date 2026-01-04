import typing

from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


T_co = typing.TypeVar("T_co", covariant=True)


class List(AbstractProvider[list[T_co]]):
    __slots__ = AbstractProvider.BASE_SLOTS

    def __init__(self, scope: Scope, *args: AbstractProvider[T_co]) -> None:
        super().__init__(scope, args=list(args))
