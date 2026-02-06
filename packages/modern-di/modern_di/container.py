import threading
import typing

import typing_extensions

from modern_di import types
from modern_di.group import Group
from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.container_provider import container_provider
from modern_di.registries.cache_registry import CacheRegistry
from modern_di.registries.context_registry import ContextRegistry
from modern_di.registries.overrides_registry import OverridesRegistry
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.scope import Scope


class Container:
    __slots__ = (
        "cache_registry",
        "context_registry",
        "lock",
        "overrides_registry",
        "parent_container",
        "providers_registry",
        "scope",
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
        self.cache_registry = CacheRegistry()
        self.context_registry = ContextRegistry(context=context or {})
        self.providers_registry: ProvidersRegistry
        self.overrides_registry: OverridesRegistry
        if parent_container:
            self.providers_registry = parent_container.providers_registry
            self.overrides_registry = parent_container.overrides_registry
        else:
            self.providers_registry = ProvidersRegistry()
            container_provider.bound_type = type(self)
            self.providers_registry.add_providers(container_provider)
            self.overrides_registry = OverridesRegistry()
        if groups:
            for one_group in groups:
                self.providers_registry.add_providers(*one_group.get_providers())

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

    def resolve(self, dependency_type: type[types.T]) -> types.T:
        provider = self.providers_registry.find_provider(dependency_type)
        if not provider:
            msg = f"Provider is not found, {dependency_type=}"
            raise RuntimeError(msg)

        return self.resolve_provider(provider)

    def resolve_provider(self, provider: "AbstractProvider[types.T]") -> types.T:
        if (override := self.overrides_registry.fetch_override(provider.provider_id)) is not None:
            return typing.cast(types.T, override)

        return typing.cast(types.T, provider.resolve(self))

    async def close_async(self) -> None:
        if not self.parent_container:
            self.overrides_registry.reset_override()
        await self.cache_registry.close_async()

    def close_sync(self) -> None:
        if not self.parent_container:
            self.overrides_registry.reset_override()
        self.cache_registry.close_sync()

    def override(self, provider: AbstractProvider[types.T], override_object: object) -> None:
        self.overrides_registry.override(provider.provider_id, override_object)

    def reset_override(self, provider: AbstractProvider[types.T] | None = None) -> None:
        self.overrides_registry.reset_override(provider.provider_id if provider else None)

    def set_context(self, context_type: type[types.T], obj: types.T) -> None:
        self.context_registry.set_context(context_type, obj)

    def __deepcopy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Prevent cloning object."""
        return self

    def __copy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Prevent cloning object."""
        return self
