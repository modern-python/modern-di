import typing

from modern_di.consts import UNSET
from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


class Object(AbstractProvider[T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "obj"]

    def __init__(
        self,
        *,
        scope: Scope = Scope.APP,
        obj: T_co,
        bound_type: type | None = UNSET,  # type: ignore[assignment]
    ) -> None:
        super().__init__(scope=scope, bound_type=bound_type if bound_type != UNSET else type(obj))
        self.obj: typing.Final = obj

    def resolve(self, _: "Container") -> T_co:
        return self.obj
