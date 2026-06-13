import enum
import typing

from modern_di import exceptions, types
from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


class Alias(AbstractProvider[types.T_co]):
    __slots__ = ("_source_type",)

    enforces_dependency_scope = False

    def __init__(
        self,
        *,
        source_type: type[types.T_co],
        scope: enum.IntEnum = Scope.APP,
        bound_type: type | None | types.UnsetType = types.UNSET,
    ) -> None:
        super().__init__(scope=scope, bound_type=source_type if isinstance(bound_type, types.UnsetType) else bound_type)
        self._source_type = source_type

    def __repr__(self) -> str:
        return f"Alias(source_type={self._source_type!r}, bound_type={self.bound_type!r}, scope={self.scope!r})"

    def _find_source(self, container: "Container") -> "AbstractProvider[types.T_co]":
        source = container.providers_registry.find_provider(self._source_type)
        if source is None:
            raise exceptions.AliasSourceNotRegisteredError(source_type=self._source_type)
        return source

    def get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:
        return {"source": self._find_source(container)}

    def resolve(self, container: "Container") -> types.T_co:
        return container.resolve_provider(self._find_source(container))
