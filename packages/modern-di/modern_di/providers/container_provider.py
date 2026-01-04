import typing

from modern_di.providers import AbstractProvider
from modern_di.scope import Scope


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class ContainerProvider(AbstractProvider[typing.Any]):
    __slots__ = AbstractProvider.BASE_SLOTS

    def __init__(self, scope: Scope) -> None:
        super().__init__(scope)
