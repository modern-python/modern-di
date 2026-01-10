import typing

from modern_di import types
from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container, types


class Object(AbstractProvider[types.T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_object"]

    def __init__(
        self,
        *,
        scope: Scope = Scope.APP,
        obj: types.T_co,
        bound_type: type | None = types.UNSET,  # type: ignore[assignment]
    ) -> None:
        super().__init__(scope=scope, bound_type=bound_type if bound_type != types.UNSET else type(obj))
        self._object = obj

    def resolve(self, _: "Container") -> types.T_co:
        return self._object
