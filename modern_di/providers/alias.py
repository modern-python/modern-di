import enum
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

    def _resolution_step(self) -> "exceptions.ResolutionStep":
        name = self.bound_type.__name__ if self.bound_type else repr(self)
        return exceptions.ResolutionStep(scope=self.scope, name=name)

    def get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:
        return {"source": self._find_source(container)}

    def effective_scope(self, container: "Container") -> enum.IntEnum:
        # Follow the alias chain to its terminal (non-alias) source and report that scope.
        seen: set[int] = set()
        provider: AbstractProvider[typing.Any] = self
        while isinstance(provider, Alias):
            if provider.provider_id in seen:
                return self.scope  # alias cycle — reported separately by validate()'s cycle check
            seen.add(provider.provider_id)
            try:
                provider = provider._find_source(container)  # noqa: SLF001
            except exceptions.AliasSourceNotRegisteredError:
                return self.scope  # dangling source — reported separately
        return provider.scope

    def resolve(self, container: "Container") -> types.T_co:
        try:
            return container.resolve_provider(self._find_source(container))
        except exceptions.ResolutionError as exc:
            exc.prepend_step(self._resolution_step())
            raise
