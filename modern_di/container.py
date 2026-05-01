import threading
import typing

import typing_extensions

from modern_di import errors, types
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
        "_resolving",
        "_scope_map",
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
        self._resolving: threading.local = parent_container._resolving if parent_container else threading.local()  # noqa: SLF001
        self._scope_map: dict[Scope, typing_extensions.Self] = (
            {**parent_container._scope_map, scope: self} if parent_container else {scope: self}  # noqa: SLF001
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
            self.providers_registry.register(type(self), container_provider)
            self.overrides_registry = OverridesRegistry()
        if groups:
            for one_group in groups:
                self.providers_registry.add_providers(*one_group.get_providers())

    def build_child_container(
        self, context: dict[type[typing.Any], typing.Any] | None = None, scope: Scope | None = None
    ) -> "typing_extensions.Self":
        if scope and scope <= self.scope:
            raise RuntimeError(
                errors.CONTAINER_SCOPE_IS_LOWER_ERROR.format(
                    parent_scope=self.scope.name,
                    child_scope=scope.name,
                    allowed_scopes=[x.name for x in Scope if x > self.scope],
                )
            )

        if not scope:
            try:
                scope = self.scope.__class__(self.scope.value + 1)
            except ValueError as exc:
                raise RuntimeError(
                    errors.CONTAINER_MAX_SCOPE_REACHED_ERROR.format(parent_scope=self.scope.name)
                ) from exc

        return self.__class__(scope=scope, parent_container=self, context=context)

    def find_container(self, scope: Scope) -> "typing_extensions.Self":
        if scope not in self._scope_map:
            if scope > self.scope:
                raise RuntimeError(
                    errors.CONTAINER_NOT_INITIALIZED_SCOPE_ERROR.format(
                        provider_scope=scope.name, container_scope=self.scope.name
                    )
                )
            raise RuntimeError(errors.CONTAINER_SCOPE_IS_SKIPPED_ERROR.format(provider_scope=scope.name))
        return self._scope_map[scope]

    def resolve(self, dependency_type: type[types.T]) -> types.T:
        provider = self.providers_registry.find_provider(dependency_type)
        if not provider:
            raise RuntimeError(errors.CONTAINER_MISSING_PROVIDER_ERROR.format(provider_type=dependency_type))

        return self.resolve_provider(provider)

    def resolve_provider(self, provider: "AbstractProvider[types.T]") -> types.T:
        if (
            self.overrides_registry.overrides
            and (override := self.overrides_registry.fetch_override(provider.provider_id)) is not types.UNSET
        ):
            return override  # ty: ignore[invalid-return-type]

        provider_id = provider.provider_id
        resolving: dict[int, AbstractProvider[typing.Any]] = getattr(self._resolving, "stack", None) or {}
        if provider_id in resolving:
            cycle_names = [p.bound_type.__name__ if p.bound_type else repr(p) for p in resolving.values()]
            cycle_names.append(provider.bound_type.__name__ if provider.bound_type else repr(provider))
            raise RuntimeError(errors.CYCLE_DEPENDENCY_ERROR.format(cycle_path=" -> ".join(cycle_names)))

        resolving[provider_id] = provider
        self._resolving.stack = resolving
        try:
            return provider.resolve(self)
        finally:
            del resolving[provider_id]

    def validate_provider(self, provider: "AbstractProvider[types.T]") -> types.T:
        return typing.cast(types.T, provider.validate(self))

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

    def __repr__(self) -> str:
        n_providers = len(self.providers_registry)
        n_cached = self.cache_registry.cached_count()
        return f"Container(scope={self.scope!r}, providers={n_providers}, cached={n_cached})"

    def __enter__(self) -> "typing_extensions.Self":
        return self

    def __exit__(self, *_: object) -> None:
        self.close_sync()

    async def __aenter__(self) -> "typing_extensions.Self":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close_async()

    def __deepcopy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Prevent cloning object."""
        return self

    def __copy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Prevent cloning object."""
        return self
