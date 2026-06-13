import enum
import threading
import typing

from modern_di import exceptions, types
from modern_di.group import Group
from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.container_provider import container_provider
from modern_di.registries.cache_registry import CacheRegistry
from modern_di.registries.context_registry import ContextRegistry
from modern_di.registries.overrides_registry import OverridesRegistry
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    import typing_extensions


class Container:
    __slots__ = (
        "cache_registry",
        "closed",
        "context_registry",
        "lock",
        "overrides_registry",
        "parent_container",
        "providers_registry",
        "scope",
        "scope_map",
    )

    def __init__(  # noqa: PLR0913
        self,
        scope: enum.IntEnum = Scope.APP,
        parent_container: typing.Optional["typing_extensions.Self"] = None,
        context: dict[type[typing.Any], typing.Any] | None = None,
        groups: list[type[Group]] | None = None,
        use_lock: bool = True,
        validate: bool = False,
    ) -> None:
        if not isinstance(scope, enum.IntEnum):
            raise exceptions.InvalidScopeTypeError(scope_value=scope)
        if parent_container is not None and scope <= parent_container.scope:
            raise exceptions.InvalidChildScopeError(
                parent_scope=parent_container.scope,
                child_scope=scope,
                allowed_scopes=[x.name for x in type(parent_container.scope) if x > parent_container.scope],
            )
        self.lock = threading.RLock() if use_lock else None
        self.closed = False
        self.scope = scope
        self.parent_container = parent_container
        self.scope_map: dict[enum.IntEnum, typing_extensions.Self] = (
            {**parent_container.scope_map, scope: self} if parent_container else {scope: self}
        )
        self.cache_registry = CacheRegistry()
        self.context_registry = ContextRegistry(context=context or {})
        self.providers_registry: ProvidersRegistry
        self.overrides_registry: OverridesRegistry
        if parent_container:
            self.providers_registry = parent_container.providers_registry
            self.overrides_registry = parent_container.overrides_registry
        else:
            self.providers_registry = ProvidersRegistry()
            self.providers_registry.register(Container, container_provider)
            self.overrides_registry = OverridesRegistry()
        if groups:
            all_providers: list[AbstractProvider[typing.Any]] = []
            for one_group in groups:
                all_providers.extend(one_group.get_providers())
            self.providers_registry.add_providers(*all_providers)
        if validate:
            self.validate()

    def build_child_container(
        self,
        *,
        scope: enum.IntEnum | None = None,
        context: dict[type[typing.Any], typing.Any] | None = None,
    ) -> "typing_extensions.Self":
        if self.closed:
            raise exceptions.ContainerClosedError(container_scope=self.scope)

        if scope is not None and scope <= self.scope:
            raise exceptions.InvalidChildScopeError(
                parent_scope=self.scope,
                child_scope=scope,
                allowed_scopes=[x.name for x in type(self.scope) if x > self.scope],
            )

        if scope is None:
            try:
                scope = self.scope.__class__(self.scope.value + 1)
            except ValueError as exc:
                raise exceptions.MaxScopeReachedError(parent_scope=self.scope) from exc

        return self.__class__(scope=scope, parent_container=self, context=context, use_lock=self.lock is not None)

    def find_container(self, scope: enum.IntEnum) -> "typing_extensions.Self":
        if scope not in self.scope_map:
            if scope > self.scope:
                raise exceptions.ScopeNotInitializedError(provider_scope=scope, container_scope=self.scope)
            raise exceptions.ScopeSkippedError(provider_scope=scope, container_scope=self.scope)
        return self.scope_map[scope]

    def resolve(self, dependency_type: type[types.T]) -> types.T:
        provider = self.providers_registry.find_provider(dependency_type)
        if not provider:
            raise exceptions.ProviderNotRegisteredError(
                provider_type=dependency_type,
                suggestions=self.providers_registry.build_suggestions(dependency_type),
            )

        return self.resolve_provider(provider)

    def resolve_provider(self, provider: "AbstractProvider[types.T]") -> types.T:
        if self.closed:
            raise exceptions.ContainerClosedError(container_scope=self.scope)

        if (
            self.overrides_registry.overrides
            and (override := self.overrides_registry.fetch_override(provider.provider_id)) is not types.UNSET
        ):
            return override  # ty: ignore[invalid-return-type]

        return provider.resolve(self)

    def validate(self) -> None:
        validation_errors: list[Exception] = []
        visiting: set[int] = set()
        visited: set[int] = set()
        path: list[AbstractProvider[typing.Any]] = []

        def _visit(provider: AbstractProvider[typing.Any]) -> None:
            pid = provider.provider_id
            if pid in visited:
                return
            if pid in visiting:
                cycle_start = next(i for i, p in enumerate(path) if p.provider_id == pid)
                cycle_names = [p.bound_type.__name__ if p.bound_type else repr(p) for p in path[cycle_start:]]
                cycle_names.append(cycle_names[0])
                validation_errors.append(exceptions.CircularDependencyError(cycle_path=cycle_names))
                return

            visiting.add(pid)
            path.append(provider)
            validation_errors.extend(provider.iter_validation_issues(self))

            try:
                dependencies = provider.get_dependencies(self)
            except exceptions.ResolutionError as exc:
                validation_errors.append(exc)
                dependencies = {}
            provider_scope = provider.effective_scope(self)
            for dep_name, dep_provider in dependencies.items():
                dep_scope = dep_provider.effective_scope(self)
                if dep_scope > provider_scope:
                    validation_errors.append(
                        exceptions.InvalidScopeDependencyError(
                            provider=provider,
                            parameter_name=dep_name,
                            dep_provider=dep_provider,
                            dep_scope=dep_scope,
                        )
                    )
                _visit(dep_provider)

            path.pop()
            visiting.discard(pid)
            visited.add(pid)

        for one_provider in self.providers_registry:
            _visit(one_provider)

        if validation_errors:
            raise exceptions.ValidationFailedError(errors=validation_errors)

    async def close_async(self) -> None:
        if not self.parent_container:
            self.overrides_registry.reset_override()
        try:
            await self.cache_registry.close_async()
        finally:
            self.closed = True

    def close_sync(self) -> None:
        if not self.parent_container:
            self.overrides_registry.reset_override()
        try:
            self.cache_registry.close_sync()
        finally:
            self.closed = True

    def override(self, provider: AbstractProvider[types.T], override_object: types.T) -> None:
        self.overrides_registry.override(provider.provider_id, override_object)

    def reset_override(self, provider: AbstractProvider[types.T] | None = None) -> None:
        self.overrides_registry.reset_override(provider.provider_id if provider else None)

    def set_context(self, context_type: type[types.T], obj: types.T) -> None:
        """Register a runtime context value on *this* container.

        A ``ContextProvider`` reads the context registry of the container at the
        provider's own scope — context never propagates between parent and child
        containers. Set the value on the container whose scope matches the
        ``ContextProvider`` (for request-scoped context, pass ``context={...}``
        to :meth:`build_child_container` or call ``set_context`` on the request
        container). Values set after a dependent factory has already resolved
        are picked up by subsequent resolves.
        """
        self.context_registry.set_context(context_type, obj)
        self.cache_registry.invalidate_compiled_kwargs()

    def __repr__(self) -> str:
        n_providers = len(self.providers_registry)
        n_cached = self.cache_registry.cached_count()
        parent = self.parent_container.scope.name if self.parent_container else None
        return f"Container(scope={self.scope.name}, parent={parent}, providers={n_providers}, cached={n_cached})"

    def __enter__(self) -> "typing_extensions.Self":
        self.closed = False
        return self

    def __exit__(self, *_: object) -> None:
        self.close_sync()

    async def __aenter__(self) -> "typing_extensions.Self":
        self.closed = False
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close_async()

    def __deepcopy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Prevent cloning object."""
        return self

    def __copy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Prevent cloning object."""
        return self
