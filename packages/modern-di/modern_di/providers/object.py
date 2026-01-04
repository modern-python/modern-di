import typing

from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class Object(AbstractProvider[T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "obj"]

    def __init__(self, scope: Scope, obj: T_co) -> None:
        super().__init__(scope)
        self.obj: typing.Final = obj
