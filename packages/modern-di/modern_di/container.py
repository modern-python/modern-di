import threading
import typing

import typing_extensions

from modern_di import types
from modern_di.group import Group
from modern_di.providers import Object
from modern_di.providers.abstract import AbstractProvider
from modern_di.registries.cache_registry import CacheRegistry
from modern_di.registries.context_registry import ContextRegistry
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.scope import Scope


T_co = typing.TypeVar("T_co", covariant=True)


class Container:
    __slots__ = (
        "cache_registry",
        "context_registry",
        "lock",
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
        if parent_container:
            self.providers_registry = parent_container.providers_registry
        else:
            self.providers_registry = ProvidersRegistry()
            self.providers_registry.add_providers(di_container=ContainerProvider())
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

        return typing.cast(T_co, provider.resolve(self))

    def resolve_provider(self, provider: "AbstractProvider[T_co]") -> T_co:
        return typing.cast(T_co, provider.resolve(self))

    async def close_async(self) -> None:
        if not self.parent_container:
            self.providers_registry.reset_override()
        await self.cache_registry.close_async()

    def close_sync(self) -> None:
        if not self.parent_container:
            self.providers_registry.reset_override()
        self.cache_registry.close_sync()

    def override(
        self,
        *,
        dependency_name: str | None = None,
        dependency_type: type[types.T_co] | None = None,
        mock: typing.Any,  # noqa: ANN401
    ) -> None:
        self.cache_registry.clear_kwargs()
        new_provider = mock if isinstance(mock, AbstractProvider) else Object(obj=mock, bound_type=dependency_type)
        return self.providers_registry.override_provider(
            dependency_name=dependency_name, dependency_type=dependency_type, new_provider=new_provider
        )

    def reset_override(
        self, *, dependency_name: str | None = None, dependency_type: type[types.T_co] | None = None
    ) -> None:
        self.cache_registry.clear_kwargs()
        return self.providers_registry.reset_override(dependency_name=dependency_name, dependency_type=dependency_type)

    def __deepcopy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Prevent cloning object."""
        return self

    def __copy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Prevent cloning object."""
        return self


class ContainerProvider(AbstractProvider[typing.Any]):
    __slots__ = AbstractProvider.BASE_SLOTS

    def __init__(self) -> None:
        super().__init__(scope=Scope.APP, bound_type=Container)

    def resolve(self, container: Container) -> Container:
        return container
