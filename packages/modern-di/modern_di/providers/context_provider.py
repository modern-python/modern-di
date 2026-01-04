import typing

from modern_di.providers import AbstractProvider
from modern_di.scope import Scope


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class ContextProvider(AbstractProvider[T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "context_type", "required"]

    def __init__(self, scope: Scope, context_type: type[T_co]) -> None:
        super().__init__(scope)
        self.context_type = context_type
