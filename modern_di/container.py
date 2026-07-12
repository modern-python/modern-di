import enum
import threading
import typing
import warnings

from modern_di import exceptions, types
from modern_di.dependency_graph import (
    Cycle,
    DependenciesError,
    DependencyGraph,
    Edge,
    NodeEntered,
    build_cycle_error,
)
from modern_di.group import Group
from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.container_provider import container_provider
from modern_di.registries.cache_registry import CacheRegistry
from modern_di.registries.context_registry import ContextRegistry
from modern_di.registries.overrides_registry import OverrideHandle, OverridesRegistry
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    import typing_extensions


class Container:
    """DI container — the central object that resolves providers within a scope.

    A root container is created with ``Container(scope=Scope.APP, groups=[...])``;
    child containers come from :meth:`build_child_container`. A child shares the
    parent's ``providers_registry`` and ``overrides_registry`` but owns its own
    ``cache_registry`` and ``context_registry``.
    """

    __slots__ = (
        "_lock",
        "_scope_map",
        "_validated",
        "cache_registry",
        "closed",
        "context_registry",
        "overrides_registry",
        "parent_container",
        "providers_registry",
        "scope",
    )

    def __init__(  # noqa: PLR0913
        self,
        scope: enum.IntEnum = Scope.APP,
        parent_container: typing.Optional["typing_extensions.Self"] = None,
        context: dict[type[typing.Any], typing.Any] | None = None,
        groups: list[type[Group]] | None = None,
        use_lock: bool = True,
        validate: bool | None = None,
    ) -> None:
        """Build a container at ``scope``.

        ``validate=True`` checks the provider graph (cycles plus scope ordering)
        at construction time; ``validate=False`` skips the check silently.
        Leaving ``validate`` unset (``None``, the default) skips the check but
        warns with :class:`~modern_di.exceptions.UnvalidatedContainerWarning` on
        a root container; child containers (with ``parent_container`` set) never
        warn. ``context`` seeds this container's context registry. A root
        container owns fresh registries; a child shares the parent's
        providers/overrides registries and inherits its scope map.
        """
        if not isinstance(scope, enum.IntEnum):
            raise exceptions.InvalidScopeTypeError(scope_value=scope)
        if parent_container is not None and scope <= parent_container.scope:
            raise exceptions.InvalidChildScopeError(
                parent_scope=parent_container.scope,
                child_scope=scope,
                allowed_scopes=[x.name for x in type(parent_container.scope) if x > parent_container.scope],
            )
        self._lock = threading.RLock() if use_lock else None
        self._validated = False
        self.closed = False
        self.scope = scope
        self.parent_container = parent_container
        self._scope_map: dict[enum.IntEnum, typing_extensions.Self] = (
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
            self.providers_registry.register(Container, container_provider)
            self.overrides_registry = OverridesRegistry()
        if groups:
            all_providers: list[AbstractProvider[typing.Any]] = []
            for one_group in groups:
                all_providers.extend(one_group.get_providers())
            self.providers_registry.add_providers(*all_providers)
        if validate:
            self.validate()
        elif validate is None and parent_container is None:
            warnings.warn(
                "This root container was created without an explicit `validate` argument. "
                "modern-di 3.0 runs validate() at root construction by default. Pass validate=True "
                "to adopt the 3.0 behavior now, or validate=False to keep validation off. "
                "See: https://modern-di.modern-python.org/migration/to-3.x/"
                "#4-validate-runs-by-default-at-root-construction",
                exceptions.UnvalidatedContainerWarning,
                stacklevel=2,
            )

    def build_child_container(
        self,
        *,
        scope: enum.IntEnum | None = None,
        context: dict[type[typing.Any], typing.Any] | None = None,
    ) -> "typing_extensions.Self":
        self._warn_and_reopen_if_closed()

        if scope is not None and scope <= self.scope:
            raise exceptions.InvalidChildScopeError(
                parent_scope=self.scope,
                child_scope=scope,
                allowed_scopes=[x.name for x in type(self.scope) if x > self.scope],
            )

        if scope is None:
            # Derive the next scope as the smallest member deeper than the current one, so
            # non-contiguous custom enums (e.g. TENANT=6, JOB=10) work, not just `value + 1`.
            deeper_scopes = [member for member in type(self.scope) if member > self.scope]
            if not deeper_scopes:
                raise exceptions.MaxScopeReachedError(parent_scope=self.scope)
            scope = min(deeper_scopes)

        return self.__class__(scope=scope, parent_container=self, context=context, use_lock=self._lock is not None)

    def find_container(self, scope: enum.IntEnum) -> "typing_extensions.Self":
        if scope not in self._scope_map:
            if scope > self.scope:
                raise exceptions.ScopeNotInitializedError(provider_scope=scope, container_scope=self.scope)
            raise exceptions.ScopeSkippedError(provider_scope=scope, container_scope=self.scope)
        return self._scope_map[scope]

    @property
    def scope_map(self) -> "dict[enum.IntEnum, typing_extensions.Self]":
        warnings.warn(
            "`Container.scope_map` is private; it will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._scope_map

    @property
    def lock(self) -> "threading.RLock | None":
        warnings.warn(
            "`Container.lock` is private; it will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._lock

    def resolve(self, dependency_type: type[types.T]) -> types.T:
        """Resolve a dependency by its type."""
        provider = self.providers_registry.find_provider(dependency_type)
        if not provider:
            raise exceptions.ProviderNotRegisteredError(
                provider_type=dependency_type,
                suggestions=self.providers_registry.build_suggestions(dependency_type),
            )

        return self.resolve_provider(provider)

    def resolve_dependency(self, dependency: "AbstractProvider[types.T] | type[types.T]") -> types.T:
        """Resolve a provider reference or a type — the marker-dispatch entry point for integrations.

        A provider argument goes to :meth:`resolve_provider`; a type argument goes to
        :meth:`resolve`. Overrides, caching, and did-you-mean suggestions are inherited
        from whichever of the two it dispatches to.
        """
        if isinstance(dependency, AbstractProvider):
            return self.resolve_provider(dependency)
        return self.resolve(dependency)

    def resolve_provider(self, provider: "AbstractProvider[types.T]") -> types.T:
        """Resolve a specific provider by reference (enforces closed-state and applies overrides)."""
        self._warn_and_reopen_if_closed()

        if (
            self.overrides_registry.overrides
            and (override := self.overrides_registry.fetch_override(provider.provider_id)) is not types.UNSET
        ):
            return override  # ty: ignore[invalid-return-type]

        try:
            return provider.resolve(self)
        except RecursionError as exc:
            reg = self.providers_registry
            if reg.validated_version == reg.version:
                raise  # validated => acyclic static graph => genuine self-recursion
            cycle = DependencyGraph().find_cycle_from(provider, self)
            if cycle is None:
                raise
            raise build_cycle_error(cycle) from exc

    def validate(self) -> None:
        reg = self.providers_registry
        if reg.validated_version == reg.version:
            self._validated = True
            return  # already validated at this registry version — no re-walk

        validation_errors: list[Exception] = []
        graph = DependencyGraph()
        for event in graph.walk(reg, self):
            match event:
                case NodeEntered(provider):
                    validation_errors.extend(provider.iter_validation_issues(self))
                case DependenciesError(_, error):
                    validation_errors.append(error)
                case Edge(parent, name, dep):
                    dep_scope = graph.terminal_scope(dep, self)
                    if dep_scope > graph.terminal_scope(parent, self):
                        validation_errors.append(
                            exceptions.InvalidScopeDependencyError(
                                provider=parent,
                                parameter_name=name,
                                dep_provider=dep,
                                dep_scope=dep_scope,
                            )
                        )
                case Cycle(providers):
                    validation_errors.append(build_cycle_error(providers))

        if validation_errors:
            raise exceptions.ValidationFailedError(errors=validation_errors)
        self._validated = True
        reg.validated_version = reg.version

    def add_providers(self, *providers: AbstractProvider[typing.Any]) -> None:
        """Register providers on this (root) container after construction.

        This is the blessed seam for framework integrations that discover providers
        after the container is built. Root-only: calling this on a child container
        raises :class:`~modern_di.exceptions.ChildContainerRegistrationError`, since
        the providers registry is shared tree-wide. If validation has run **on this
        container** (via ``validate=True`` at construction or a manual :meth:`validate`
        call — ``_validated`` is per-container, not inherited from a parent), it is
        re-validated after registering, so a newly-added provider that breaks the
        graph raises :class:`~modern_di.exceptions.ValidationFailedError` here rather
        than later. Atomic: if that re-validation raises *any* exception, the whole
        batch is removed again before the error propagates — either the batch is
        fully registered and valid, or the container is unchanged. Registration is a
        startup-time operation: concurrent ``add_providers`` calls on the same root
        are not coordinated beyond the registry's internal lock.
        """
        if self.parent_container is not None:
            raise exceptions.ChildContainerRegistrationError(scope=self.scope)
        self.providers_registry.add_providers(*providers)
        if self._validated:
            try:
                self.validate()
            except Exception:
                added_types = [provider.bound_type for provider in providers if provider.bound_type]
                self.providers_registry._remove_providers(*added_types)  # noqa: SLF001
                raise

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

    def override(self, provider: AbstractProvider[types.T], override_object: types.T) -> OverrideHandle[types.T]:
        """Apply an override immediately.

        Use the returned handle as a context manager to auto-restore the prior state.
        """
        prior = self.overrides_registry.fetch_override(provider.provider_id)
        self.overrides_registry.override(provider.provider_id, override_object)
        return OverrideHandle(
            registry=self.overrides_registry,
            provider_id=provider.provider_id,
            prior=prior,
            override_object=override_object,
        )

    def reset_override(self, provider: AbstractProvider[types.T] | None = None) -> None:
        self.overrides_registry.reset_override(provider.provider_id if provider else None)

    def set_context(self, context_type: type[types.T], obj: types.T) -> None:
        """Register a runtime context value on *this* container.

        Context never propagates between parent and child containers — set it
        on the container whose scope matches the ``ContextProvider``. A
        **cached** provider (``Factory(cache=...)``) is built once and its
        instance is *not* rebuilt by a later ``set_context``; set the context
        before its first resolve.
        """
        self.context_registry.set_context(context_type, obj)

    def __repr__(self) -> str:
        n_providers = len(self.providers_registry)
        n_cached = self.cache_registry.cached_count()
        parent = self.parent_container.scope.name if self.parent_container else None
        return f"Container(scope={self.scope.name}, parent={parent}, providers={n_providers}, cached={n_cached})"

    def open(self) -> None:
        """Reopen a closed container so it can resolve and build children again.

        Called by ``__enter__``/``__aenter__`` to reopen on re-entry. Use it
        directly when a callback-style lifecycle (e.g. a startup hook) cannot
        wrap the container in a ``with`` block. Reopening an already-open
        container is a no-op.
        """
        self.closed = False

    def _warn_and_reopen_if_closed(self) -> None:
        """Transitional shim for reuse of a closed container.

        Emits :class:`~modern_di.exceptions.ContainerClosedWarning` and reopens.
        Fires once per container transitioning from closed to reopened; an
        already-open container emits none.
        """
        if not self.closed:
            return
        warnings.warn(
            f"Container (scope {self.scope.name}) is closed; resolving from it or building a child "
            "is deprecated and will raise ContainerClosedError in modern-di 3.0. Re-enter the "
            "container with `with`/`async with`, or call `open()`, before reusing it. "
            "See: https://modern-di.modern-python.org/migration/to-3.x/"
            "#1-closed-containers-raise-instead-of-self-healing",
            exceptions.ContainerClosedWarning,
            stacklevel=2,
        )
        self.open()

    def __enter__(self) -> "typing_extensions.Self":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close_sync()

    async def __aenter__(self) -> "typing_extensions.Self":
        self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close_async()

    def __deepcopy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Prevent cloning object."""
        return self

    def __copy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Prevent cloning object."""
        return self
