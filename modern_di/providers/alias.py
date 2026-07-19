import typing

from modern_di import exceptions, types
from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


class Alias(AbstractProvider[types.T_co]):
    __slots__ = ("_source_type",)

    def __init__(
        self,
        source_type: type[types.T_co],
        *,
        bound_type: type | None | types.UnsetType = types.UNSET,
    ) -> None:
        # Always a concrete IntEnum (never UNSET), so `_scope_defaulted` stays False and
        # group-default stamping skips aliases. An alias's effective scope is derived from its source.
        super().__init__(
            scope=Scope.APP, bound_type=source_type if isinstance(bound_type, types.UnsetType) else bound_type
        )
        self._source_type = source_type

    def __repr__(self) -> str:
        return f"Alias(source_type={self._source_type!r}, bound_type={self.bound_type!r}, scope={self.scope!r})"

    def _find_source(self, container: "Container") -> "AbstractProvider[types.T_co]":
        source = container.providers_registry.find_provider(self._source_type)
        if source is None:
            raise exceptions.AliasSourceNotRegisteredError(source_type=self._source_type)
        return source

    def _resolution_step(self) -> "exceptions.ResolutionStep":
        return exceptions.ResolutionStep(scope=self.scope, name=self.display_name)

    def get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:
        return {"source": self._find_source(container)}

    def redirect_target(self, container: "Container") -> "AbstractProvider[typing.Any] | None":
        try:
            return self._find_source(container)
        except exceptions.AliasSourceNotRegisteredError:
            return None
