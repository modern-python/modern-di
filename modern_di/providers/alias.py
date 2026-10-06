import typing

from modern_di import exceptions, types
from modern_di.providers.abstract import AbstractProvider


if typing.TYPE_CHECKING:
    from modern_di.registries.providers_registry import ProvidersRegistry


class Alias(AbstractProvider[types.T_co]):
    __slots__ = ("_source_type",)

    _takes_group_scope = False

    def __init__(
        self,
        source_type: type[types.T_co],
        *,
        bound_type: type | types.UnsetType | None = types.UNSET,
    ) -> None:
        super().__init__(scope=types.UNSET, bound_type=bound_type, inferred_bound_type=source_type)
        self._source_type = source_type

    def __repr__(self) -> str:
        return f"Alias(source_type={self._source_type!r}, bound_type={self.bound_type!r}, scope={self.scope!r})"

    def _get_dependencies(self, registry: "ProvidersRegistry") -> dict[str, "AbstractProvider[typing.Any]"]:
        source = self._redirect_target(registry)
        if source is None:
            raise exceptions.AliasSourceNotRegisteredError(source_type=self._source_type)
        return {"source": source}

    def _redirect_target(self, registry: "ProvidersRegistry") -> "AbstractProvider[typing.Any] | None":
        return registry.find_provider(self._source_type)
