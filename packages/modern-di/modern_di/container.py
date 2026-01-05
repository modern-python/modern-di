import threading
import typing

import typing_extensions

from modern_di.group import Group
from modern_di.registries.context_registry import ContextRegistry
from modern_di.registries.overrides_registry import OverridesRegistry
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.registries.state_registry import StateRegistry
from modern_di.resolvers import RESOLVERS
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di.providers.abstract import AbstractProvider

T_co = typing.TypeVar("T_co", covariant=True)


class Container:
    __slots__ = (
        "context_registry",
        "lock",
        "overrides_registry",
        "parent_container",
        "providers_registry",
        "scope",
        "state_registry",
    )

    def __init__(
        self,
        scope: Scope = Scope.APP,
        parent_container: typing.Optional["typing_extensions.Self"] = None,
        context: dict[type[typing.Any], typing.Any] | None = None,
        groups: list[type[Group]] | None = None,
        use_lock: bool = True,
    ) -> None:
        self.lock = threading.Lock() if use_lock else None
        self.scope = scope
        self.parent_container = parent_container
        self.state_registry = StateRegistry()
        self.context_registry = ContextRegistry(context=context or {})
        self.providers_registry: ProvidersRegistry
        self.overrides_registry: OverridesRegistry
        if parent_container:
            self.providers_registry = parent_container.providers_registry
            self.overrides_registry = parent_container.overrides_registry
        else:
            self.providers_registry = ProvidersRegistry()
            self.overrides_registry = OverridesRegistry()
        if groups:
            for one_group in groups:
                self.providers_registry.add_providers(**one_group.get_providers())

    def build_child_container(
        self, context: dict[type[typing.Any], typing.Any] | None = None, scope: Scope | None = None
    ) -> "typing_extensions.Self":
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

    def override(self, provider: "AbstractProvider[T_co]", override_object: object) -> None:
        self.overrides_registry.override(provider.provider_id, override_object)

    def reset_override(self, provider: typing.Optional["AbstractProvider[T_co]"] = None) -> None:
        self.overrides_registry.reset_override(provider.provider_id if provider else None)

    def find_container(self, scope: Scope) -> "typing_extensions.Self":
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

    def resolve(self, dependency_type: type[T_co] | None = None, *, dependency_name: str | None = None) -> T_co:
        provider = self.providers_registry.find_provider(
            dependency_type=dependency_type, dependency_name=dependency_name
        )
        if not provider:
            msg = f"Provider is not found, {dependency_type=}, {dependency_name=}"
            raise RuntimeError(msg)

        return self.resolve_provider(provider)

    def resolve_provider(self, provider: "AbstractProvider[T_co]") -> T_co:
        resolver = RESOLVERS[type(provider)]
        return typing.cast(T_co, resolver(self.find_container(provider.scope), provider))

    def __deepcopy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Prevent cloning object."""
        return self

    def __copy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Prevent cloning object."""
        return self
