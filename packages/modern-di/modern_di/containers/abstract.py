import enum
import typing

from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.context_provider import ContextProvider
from modern_di.registries.context_registry import ContextRegistry
from modern_di.registries.overrides_registry import OverridesRegistry
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    import typing_extensions


T_co = typing.TypeVar("T_co", covariant=True)


class AbstractContainer:
    BASE_SLOTS: typing.ClassVar = (
        "_is_entered",
        "state_registry",
        "context",
        "parent_container",
        "scope",
        "overrides_registry",
    )

    def __init__(
        self,
        *,
        scope: Scope = Scope.APP,
        parent_container: typing.Optional["typing_extensions.Self"] = None,
        context: dict[type[typing.Any], typing.Any] | None = None,
        providers_registry: ProvidersRegistry | None = None,
    ) -> None:
        self._is_entered = False
        self.scope = scope
        self.parent_container = parent_container
        self.providers_registry = providers_registry
        self.overrides_registry: OverridesRegistry
        self.context_registry = ContextRegistry(context or {})
        if parent_container:
            self.overrides_registry = parent_container.overrides_registry
        else:
            self.overrides_registry = OverridesRegistry()

    def _check_entered(self) -> None:
        if not self._is_entered:
            msg = f"Enter the context of {self.scope.name} scope"
            raise RuntimeError(msg)

    def resolve_context_provider(self, provider: ContextProvider[T_co]) -> T_co:
        context = self.context_registry.find_context(provider.context_type)
        if not context:
            msg = f"Context of type {provider.context_type} is missing"
            raise RuntimeError(msg)

        return context

    def build_child_container(
        self, context: dict[type[typing.Any], typing.Any] | None = None, scope: Scope | None = None
    ) -> "typing_extensions.Self":
        self._check_entered()
        if scope and scope <= self.scope:
            msg = "Scope of child container must be more than current scope"
            raise RuntimeError(msg)

        if not scope:
            try:
                scope = self.scope.__class__(self.scope.value + 1)
            except ValueError as exc:
                msg = f"Max scope is reached, {self.scope.name}"
                raise RuntimeError(msg) from exc

        return self.__class__(scope=scope, parent_container=self, context=context)

    def find_container(self, scope: enum.IntEnum) -> "typing_extensions.Self":
        container = self
        if container.scope < scope:
            msg = f"Scope {scope.name} is not initialized"
            raise RuntimeError(msg)

        while container.scope > scope and container.parent_container:
            container = container.parent_container

        if container.scope != scope:
            msg = f"Scope {scope.name} is skipped"
            raise RuntimeError(msg)

        return container

    def override(self, provider: AbstractProvider[T_co], override_object: object) -> None:
        self.overrides_registry.override(provider.provider_id, override_object)

    def reset_override(self, provider: AbstractProvider[T_co] | None = None) -> None:
        self.overrides_registry.reset_override(provider.provider_id if provider else None)

    def __deepcopy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Hack to prevent cloning object."""
        return self

    def __copy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Hack to prevent cloning object."""
        return self
