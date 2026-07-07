import enum
import typing
import warnings

from modern_di import exceptions, types
from modern_di.providers import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


class ContextProvider(AbstractProvider[types.T_co]):
    """Provider for a runtime value supplied at container-build time.

    The value is passed via ``build_child_container(context={SomeType: value})``
    and looked up from the context registry at this provider's bound scope.
    Resolving it directly when no value is set emits :class:`~modern_di.exceptions.ContextValueNoneWarning`
    and returns ``None``; injecting it into a non-nullable, no-default ``Factory``
    parameter instead raises ``ArgumentResolutionError``.
    """

    __slots__ = ("context_type",)

    def __init__(
        self,
        *,
        scope: enum.IntEnum = Scope.APP,
        context_type: type[types.T_co],
        bound_type: type | None | types.UnsetType = types.UNSET,
    ) -> None:
        super().__init__(
            scope=scope, bound_type=context_type if isinstance(bound_type, types.UnsetType) else bound_type
        )
        self.context_type = context_type

    def __repr__(self) -> str:
        return f"ContextProvider(context_type={self.context_type!r}, scope={self.scope!r})"

    def resolve(self, container: "Container") -> types.T_co | None:
        value = self.fetch_context_value(container)
        if value is types.UNSET:
            warnings.warn(
                f"No context value is set for {self.context_type!r} (scope {self.scope.name}); returning None. "
                "modern-di 3.0 raises ContextValueNotSetError here. Pass context={...} to the container or call "
                "set_context(). See https://modern-di.modern-python.org/migration/to-3.x/.",
                exceptions.ContextValueNoneWarning,
                stacklevel=2,
            )
            return None
        return typing.cast(types.T_co, value)

    def fetch_context_value(self, container: "Container") -> types.T_co | object:
        container = container.find_container(self.scope)
        container._warn_and_reopen_if_closed()  # noqa: SLF001
        return container.context_registry.find_context(self.context_type)
