import typing

from modern_di import exceptions, types
from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


class Alias(AbstractProvider[types.T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "_source_type"]

    def __init__(
        self,
        *,
        source_type: type[types.T_co],
        scope: Scope = Scope.APP,
        bound_type: type | None = types.UNSET,  # ty: ignore[invalid-parameter-default]
    ) -> None:
        super().__init__(scope=scope, bound_type=bound_type if bound_type != types.UNSET else source_type)
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

    def validate(self, container: "Container") -> dict[str, typing.Any]:
        source = self._find_source(container)
        return {
            "bound_type": self.bound_type,
            "source_type": self._source_type,
            "source": source.validate(container),
            "self": self,
        }

    def resolve(self, container: "Container") -> types.T_co:
        return container.resolve_provider(self._find_source(container))
