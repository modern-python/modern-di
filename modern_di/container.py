import copy
import enum
import typing

from modern_di import dependency_graph, exceptions, types
from modern_di._scope_algebra import next_deeper
from modern_di.group import Group
from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.container_provider import container_provider
from modern_di.registries.cache_registry import CacheRegistry
from modern_di.registries.context_registry import ContextRegistry
from modern_di.registries.overrides_registry import OverrideHandle
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.resolver_compiler import STEP_ERRORS
from modern_di.scope import Scope


def _handle_recursion_error(
    provider: AbstractProvider[typing.Any], container: "Container", registry: ProvidersRegistry, exc: RecursionError
) -> typing.NoReturn:
    """Convert an escaped `RecursionError` to `CircularDependencyError`, or re-raise it unchanged."""
    if registry.is_validated():
        raise exc  # validated => acyclic static graph => genuine self-recursion
    cycle = dependency_graph.find_cycle_from(provider, container)
    if cycle is None:
        raise exc
    raise dependency_graph.build_cycle_error(cycle, container) from exc


class Container:
    """DI container — the central object that resolves providers within a scope.

    A root is built as ``Container(scope=Scope.APP, groups=[...])``; children come from
    :meth:`build_child_container` and share the parent's providers and overrides registries
    while owning their own cache and context.
    """

    __slots__ = (
        "_cache_registry",
        "_closed",
        "_context_registry",
        "_providers_registry",
        "_scope_map",
        "parent_container",
        "scope",
    )

    def __init__(
        self,
        scope: enum.IntEnum = Scope.APP,
        *,
        parent_container: typing.Self | None = None,
        context: dict[type[typing.Any], typing.Any] | None = None,
        groups: list[type[Group]] | None = None,
    ) -> None:
        """Build a container at ``scope``, open and ready to :meth:`resolve`.

        ``context`` is copied into the context registry, so later changes to the caller's dict are
        not seen and :meth:`set_context` never writes into it. A root binds :class:`Container`
        itself, so ``resolve(Container)`` returns the resolving container. A cached factory creates at
        most one instance per cache key across the tree, whichever threads resolve it.

        Raises :class:`~modern_di.exceptions.InvalidScopeTypeError` when ``scope`` is not an
        ``IntEnum``, :class:`~modern_di.exceptions.InvalidChildScopeError` when it is not deeper
        than ``parent_container``'s, and
        :class:`~modern_di.exceptions.ChildContainerRegistrationError` when ``groups`` is passed
        with ``parent_container``.
        """
        if not isinstance(scope, enum.IntEnum):
            raise exceptions.InvalidScopeTypeError(scope_value=scope)
        if parent_container is not None and scope <= parent_container.scope:
            raise exceptions.InvalidChildScopeError(parent_scope=parent_container.scope, child_scope=scope)
        if parent_container is not None and groups:
            raise exceptions.ChildContainerRegistrationError(scope=scope)
        self._closed = False
        self.scope = scope
        self.parent_container = parent_container
        # Ancestors only: a `scope: self` entry is a reference cycle that refcounting never frees.
        self._scope_map: dict[enum.IntEnum, typing.Self] = (
            {**parent_container._scope_map, parent_container.scope: parent_container}  # noqa: SLF001
            if parent_container
            else {}
        )
        self._cache_registry = CacheRegistry()
        self._context_registry = ContextRegistry(copy.copy(context) if context is not None else {})
        self._providers_registry: ProvidersRegistry
        if parent_container:
            self._providers_registry = parent_container._providers_registry  # noqa: SLF001
        else:
            self._providers_registry = ProvidersRegistry()
            self._providers_registry.register(Container, container_provider)
        if groups:
            all_providers: list[AbstractProvider[typing.Any]] = []
            for one_group in groups:
                all_providers.extend(one_group.get_providers())
            self._providers_registry.add_providers(*all_providers)

    @property
    def closed(self) -> bool:
        """Whether this container is closed; :meth:`open` and re-entering ``with`` reopen it."""
        return self._closed

    def build_child_container(
        self,
        *,
        scope: enum.IntEnum | None = None,
        context: dict[type[typing.Any], typing.Any] | None = None,
    ) -> typing.Self:
        """Return a new open child at ``scope``, seeded with ``context``.

        The child shares this container's providers and overrides and owns its own cache and
        context. Without ``scope`` it takes the next deeper member of the scope enum. Raises
        :class:`~modern_di.exceptions.MaxScopeReachedError` when there is none, and
        :class:`~modern_di.exceptions.InvalidChildScopeError` when ``scope`` is not deeper.
        """
        if scope is None:
            scope = next_deeper(self.scope)
            if scope is None:
                raise exceptions.MaxScopeReachedError(parent_scope=self.scope)

        return self.__class__(scope=scope, parent_container=self, context=context)

    def find_container(self, scope: enum.IntEnum) -> typing.Self:
        """Return the container at ``scope``: this one or an ancestor.

        Raises :class:`~modern_di.exceptions.ScopeNotInitializedError` when ``scope`` is deeper
        than this container, and :class:`~modern_di.exceptions.ScopeSkippedError` when no
        ancestor was built at ``scope``.
        """
        if scope is self.scope:
            return self
        target = self._scope_map.get(scope)
        if target is None or target.scope is not scope:
            if scope > self.scope:
                raise exceptions.ScopeNotInitializedError(provider_scope=scope, container_scope=self.scope)
            raise exceptions.ScopeSkippedError(provider_scope=scope, container_scope=self.scope)
        return target

    def resolve(self, dependency_type: type[types.T]) -> types.T:
        """Resolve a dependency by its type.

        Raises :class:`~modern_di.exceptions.ContainerClosedError` when this container, or the
        ancestor a provider resolves in, is closed.
        """
        registry = self._providers_registry
        try:
            if self._closed:
                raise exceptions.ContainerClosedError(container_scope=self.scope)
            resolver = registry._resolvers_by_type.get(dependency_type)  # noqa: SLF001
            if resolver is None:
                resolver = registry.resolver_for_type(dependency_type)
            return resolver(self)
        except RecursionError as exc:
            _handle_recursion_error(registry._providers[dependency_type], self, registry, exc)  # noqa: SLF001
        except STEP_ERRORS as exc:
            provider = registry.find_provider(dependency_type)
            if provider is not None:
                exc.prepend_step(*dependency_graph.redirect_hops(provider, self))
            raise

    def resolve_dependency(self, dependency: "AbstractProvider[types.T] | type[types.T]") -> types.T:
        """Resolve a provider reference via :meth:`resolve_provider`, or a type via :meth:`resolve`."""
        if isinstance(dependency, AbstractProvider):
            return self.resolve_provider(dependency)
        return self.resolve(dependency)

    def resolve_provider(self, provider: "AbstractProvider[types.T]") -> types.T:
        """Resolve a specific provider by reference via its compiled resolver.

        Raises :class:`~modern_di.exceptions.ContainerClosedError` when this container, or the
        ancestor the provider resolves in, is closed.
        """
        if self._closed:
            raise exceptions.ContainerClosedError(container_scope=self.scope)
        registry = self._providers_registry
        try:
            resolver = registry._resolvers.get(provider.provider_id)  # noqa: SLF001
            if resolver is None:
                resolver = registry.resolver_for(provider)
            return resolver(self)
        except RecursionError as exc:
            _handle_recursion_error(provider, self, registry, exc)
        except STEP_ERRORS as exc:
            exc.prepend_step(*dependency_graph.redirect_hops(provider, self))
            raise

    def validate(self) -> None:
        """Walk the static provider graph and raise on any wiring error.

        Checks cycles, transitive scope ordering and unresolvable dependencies, aggregating every
        error into one :class:`~modern_di.exceptions.ValidationFailedError`. The only thing that
        validates — construction, :meth:`open`, :meth:`add_providers` and :meth:`resolve` never
        do. A clean walk is memoized until the registry changes.
        """
        reg = self._providers_registry
        if reg.is_validated():
            return

        if errors := dependency_graph.collect_errors(self, reg):
            raise exceptions.ValidationFailedError(errors=errors)
        reg.mark_validated()

    def add_providers(self, *providers: AbstractProvider[typing.Any]) -> None:
        """Register providers on this root container after construction.

        Root-only: on a child this raises
        :class:`~modern_di.exceptions.ChildContainerRegistrationError`, because the registry is
        shared tree-wide. Does not validate, but clears the validated flag so a later
        :meth:`validate` re-walks. A startup-time operation, not coordinated with concurrent
        resolves.
        """
        if self.parent_container is not None:
            raise exceptions.ChildContainerRegistrationError(scope=self.scope)
        self._providers_registry.add_providers(*providers)

    def find_provider(self, dependency_type: type[types.T]) -> AbstractProvider[types.T] | None:
        """Return the provider registered for ``dependency_type`` anywhere in the tree, or ``None``.

        A pure lookup: it ignores overrides and the closed state, and never compiles or resolves.
        """
        return self._providers_registry.find_provider(dependency_type)

    async def close_async(self) -> None:
        """Mark this container closed, then run its finalizers, sync and async, newest first.

        Overrides are kept. A resolve from inside a finalizer raises
        :class:`~modern_di.exceptions.ContainerClosedError`. Every finalizer runs even when one
        raises; the failures come back together as one :class:`~modern_di.exceptions.FinalizerError`.
        """
        self._closed = True
        if self._cache_registry._creation_order:  # noqa: SLF001
            await self._cache_registry.close_async()

    def close_sync(self) -> None:
        """Mark this container closed, then run its sync finalizers, newest first.

        Overrides are kept. A resolve from inside a finalizer raises
        :class:`~modern_di.exceptions.ContainerClosedError`. Every finalizer runs even when one
        raises; the failures come back together as one :class:`~modern_di.exceptions.FinalizerError`.
        An async finalizer fails here and stays pending for a later :meth:`close_async`.
        """
        self._closed = True
        if self._cache_registry._creation_order:  # noqa: SLF001
            self._cache_registry.close_sync()

    def override(self, provider: AbstractProvider[types.T], override_object: types.T) -> OverrideHandle[types.T]:
        """Apply an override immediately, tree-wide.

        Use the returned handle as a context manager to restore the prior state. A test-time
        operation, not coordinated with concurrent resolves on other threads.
        """
        overrides = self._providers_registry.overrides
        prior = overrides.fetch_override(provider.provider_id)
        overrides.override(provider.provider_id, override_object)
        return OverrideHandle(
            registry=overrides,
            provider_id=provider.provider_id,
            prior=prior,
            override_object=override_object,
        )

    def reset_override(self, provider: AbstractProvider[types.T] | None = None) -> None:
        """Drop the override on ``provider``, or every override when ``provider`` is ``None``.

        Applies tree-wide. Resetting a provider that has no override is a no-op.
        """
        self._providers_registry.overrides.reset_override(provider.provider_id if provider else None)

    def set_context(self, context_type: type[types.T], obj: types.T) -> None:
        """Register a runtime context value on *this* container.

        Context never propagates between parent and child — set it on the container whose scope
        matches the ``ContextProvider``. A cached provider is built once and is not rebuilt by a
        later ``set_context``; set the context before its first resolve.
        """
        self._context_registry.set_context(context_type, obj)

    def __repr__(self) -> str:
        n_providers = len(self._providers_registry)
        n_cached = self._cache_registry.cached_count()
        parent = self.parent_container.scope.name if self.parent_container else None
        return f"Container(scope={self.scope.name}, parent={parent}, providers={n_providers}, cached={n_cached})"

    def open(self) -> None:
        """Reopen a closed container; a no-op on an open one, and never validates.

        A constructed container is already open. After a close, resolving raises
        :class:`~modern_di.exceptions.ContainerClosedError` until this, or re-entering the
        container with ``with``/``async with``, reopens it.
        """
        self._closed = False

    def __enter__(self) -> typing.Self:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close_sync()

    async def __aenter__(self) -> typing.Self:
        self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close_async()

    def __copy__(self, *_: object, **__: object) -> typing.Self:
        """Never clone: a copied container would own a detached cache whose finalizers never run."""
        return self

    __deepcopy__ = __copy__
