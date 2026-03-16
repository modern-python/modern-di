import typing

from modern_di import types
from modern_di.providers import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


class ContextProvider(AbstractProvider[types.T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_context_type"]

    def __init__(
        self,
        *,
        scope: Scope = Scope.APP,
        context_type: type[types.T_co],
        bound_type: type | None = types.UNSET,  # type: ignore[assignment]
    ) -> None:
        super().__init__(scope=scope, bound_type=bound_type if bound_type != types.UNSET else context_type)

    def validate(self, container: "Container") -> dict[str, typing.Any]:  # noqa: ARG002
        return {"bound_type": self.bound_type, "self": self}

    def resolve(self, container: "Container") -> types.T_co | None:
        container = container.find_container(self.scope)
        return container.context_registry.find_context(typing.cast(type[types.T_co], self.bound_type))
