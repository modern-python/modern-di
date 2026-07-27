import contextlib
import enum
import threading
import typing
import warnings

from modern_di import exceptions, suggester, types
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
from modern_di.scope import Scope, _next_deeper


if typing.TYPE_CHECKING:
    import typing_extensions


def _handle_recursion_error(
    provider: AbstractProvider[typing.Any], container: "Container", exc: RecursionError
) -> typing.NoReturn:
    """Convert an escaped `RecursionError` to `CircularDependencyError`, or re-raise it unchanged.

    Split out of `resolve_provider` into its own call so the coverage tracer gets a fresh call
    boundary to re-arm on before raising.
    """
    reg = container.providers_registry
    if reg.is_validated():
        raise exc  # validated => acyclic static graph => genuine self-recursion
    cycle = DependencyGraph().find_cycle_from(provider, container)
    if cycle is None:
        raise exc
    raise build_cycle_error(cycle) from exc


class Container:
    """DI container — the central object that resolves providers within a scope.

    A root container is created with ``Container(scope=Scope.APP, groups=[...])``;
    child containers come from :meth:`build_child_container`. A child shares the
    parent's ``providers_registry`` and ``overrides_registry`` but owns its own
    ``cache_registry`` and ``context_registry``.
    """

    __slots__ = (
        "_ever_opened",
        "_lock",
        "_scope_map",
        "_validate_enabled",
        "cache_registry",
        "closed",
        "context_registry",
        "overrides_registry",
        "parent_container",
        "providers_registry",
        "scope",
    )

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        scope: enum.IntEnum = Scope.APP,
        parent_container: typing.Optional["typing_extensions.Self"] = None,
        context: dict[type[typing.Any], typing.Any] | None = None,
        groups: list[type[Group]] | None = None,
        use_lock: bool = True,
        validate: bool = True,
    ) -> None:
        """Build a container at ``scope``.

        A container is usable as soon as it is constructed: the first :meth:`resolve`
        prepares it (runs any deferred validation and marks it open). :meth:`open` and
        ``with`` / ``async with`` stay available for fail-fast startup and for running
        finalizers on the way out.

        ``validate`` (default ``True``) enables the provider-graph check (cycles,
        scope ordering, missing dependencies), whose monotone half (cycles, inverted
        scopes) runs in ``__init__`` and whose completeness half runs once at first use.
        Deferring completeness lets a framework integration register its context
        providers after construction and still have the complete graph validated.
        ``validate=False`` disables the check entirely; call :meth:`validate` explicitly
        for a construction-time check. Only a root container validates; children (with
        ``parent_container`` set) never do. ``context`` seeds this container's
        context registry. A root container owns fresh registries; a child shares
        the parent's providers/overrides registries and inherits its scope map.
        """
        if not isinstance(scope, enum.IntEnum):
            raise exceptions.InvalidScopeTypeError(scope_value=scope)
        if parent_container is not None and scope <= parent_container.scope:
            raise exceptions.InvalidChildScopeError(parent_scope=parent_container.scope, child_scope=scope)
        self._lock = threading.RLock() if use_lock else None
        self.closed = True  # not open yet; the first resolve prepares it
        self._ever_opened = False
        self.scope = scope
        self.parent_container = parent_container
        self._scope_map: dict[enum.IntEnum, typing_extensions.Self] = (
            {**parent_container._scope_map, scope: self} if parent_container else {scope: self}  # noqa: SLF001
        )
        self.cache_registry = CacheRegistry()
        self.context_registry = ContextRegistry(context=context or {})
        self.providers_registry: ProvidersRegistry
        self.overrides_registry: OverridesRegistry
        # Inlined, not a helper: __init__ is on the per-request child-build path, so avoid the extra
        # call frame. A root seeds container_provider so `Container` resolves to the resolving container.
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
        # Root-only. Monotone issues (cycles, inverted scopes) raise here: registering more providers
        # can only add such an error, never remove one. Completeness is held for first use.
        self._validate_enabled = validate and parent_container is None
        if self._validate_enabled:
            self.providers_registry.set_validation_enabled(enabled=True)
            self._eager_validate()

    def build_child_container(
        self,
        *,
        scope: enum.IntEnum | None = None,
        context: dict[type[typing.Any], typing.Any] | None = None,
    ) -> "typing_extensions.Self":
        if scope is None:
            # `_next_deeper` is the smallest member deeper than this one, so non-contiguous
            # custom enums (e.g. TENANT=6, JOB=10) work, not just `value + 1`.
            scope = _next_deeper(self.scope)
            if scope is None:
                raise exceptions.MaxScopeReachedError(parent_scope=self.scope)

        # An explicitly-passed scope is not checked here: __init__ rejects a scope that is not
        # deeper than its parent's, raising an identical InvalidChildScopeError.
        return self.__class__(scope=scope, parent_container=self, context=context, use_lock=self._lock is not None)

    def find_container(self, scope: enum.IntEnum) -> "typing_extensions.Self":
        if scope == self.scope:
            return self
        target = self._scope_map.get(scope)
        if target is None:
            if scope > self.scope:
                raise exceptions.ScopeNotInitializedError(provider_scope=scope, container_scope=self.scope)
            raise exceptions.ScopeSkippedError(provider_scope=scope, container_scope=self.scope)
        return target

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
                suggestions=suggester.suggest(dependency_type, self.providers_registry),
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
        """Resolve a specific provider by reference via its compiled resolver."""
        if self.closed:
            self._prepare()
        try:
            return self.providers_registry.resolver_for(provider)(self)
        except RecursionError as exc:
            _handle_recursion_error(provider, self, exc)

    def _walk_errors(self) -> list[tuple[bool, Exception]]:
        """Walk the graph once, returning `(is_monotone, error)` in walk order.

        Monotone errors (cycles, inverted scopes) can only be *added* by registering more
        providers, so they are safe to raise against a graph that is not yet complete.
        """
        walked: list[tuple[bool, Exception]] = []
        graph = DependencyGraph()
        for event in graph.walk(self.providers_registry, self):
            # Event is a closed 4-variant union — every variant handled below.
            match event:
                case NodeEntered(provider):
                    walked.extend((False, issue) for issue in provider.iter_validation_issues(self))
                case DependenciesError(_, error):
                    walked.append((False, error))
                case Edge(parent, name, dep):
                    dep_scope = graph.terminal_scope(dep, self)
                    if dep_scope > graph.terminal_scope(parent, self):
                        walked.append(
                            (
                                True,
                                exceptions.InvalidScopeDependencyError(
                                    provider=parent,
                                    parameter_name=name,
                                    dep_provider=dep,
                                    dep_scope=dep_scope,
                                ),
                            )
                        )
                case Cycle(providers):
                    walked.append((True, build_cycle_error(providers)))
        return walked

    def validate(self) -> None:
        reg = self.providers_registry
        if reg.is_validated():
            return  # already validated at this registry state — no re-walk

        validation_errors = [error for _, error in self._walk_errors()]
        if validation_errors:
            raise exceptions.ValidationFailedError(errors=validation_errors)
        reg.mark_validated()

    def _eager_validate(self) -> None:
        """Raise the graph's monotone issues now; hold its completeness issues for first use."""
        walked = self._walk_errors()
        monotone = [error for is_monotone, error in walked if is_monotone]
        if monotone:
            raise exceptions.ValidationFailedError(errors=monotone)
        pending = [error for is_monotone, error in walked if not is_monotone]
        if pending:
            self.providers_registry.set_pending_errors(pending)
        else:
            self.providers_registry.mark_validated()

    def _complete_validation(self) -> None:
        """Finish the deferred half of the check: raise the held issues, or re-walk if the graph moved."""
        reg = self.providers_registry
        pending = reg.take_pending_errors()
        if pending:
            raise exceptions.ValidationFailedError(errors=pending)
        self.validate()

    def add_providers(self, *providers: AbstractProvider[typing.Any]) -> None:
        """Register providers on this (root) container after construction.

        This is the blessed seam for framework integrations that discover providers
        after the container is built. Root-only: calling this on a child container
        raises :class:`~modern_di.exceptions.ChildContainerRegistrationError`, since
        the providers registry is shared tree-wide. If validation is enabled, the
        monotone half (cycles, inverted scopes) re-runs immediately against the new
        graph; the completeness half (missing dependencies, dangling aliases) is
        re-deferred to first use, since a later ``add_providers`` call may still
        complete the graph. Atomic: if the monotone re-check raises *any* exception,
        the whole batch is removed again before the error propagates — either the
        batch is fully registered, or the container is unchanged. Registration is a
        startup-time operation: concurrent ``add_providers`` calls on the same root
        are not coordinated beyond the registry's internal lock.
        """
        if self.parent_container is not None:
            raise exceptions.ChildContainerRegistrationError(scope=self.scope)
        reg = self.providers_registry
        # Read before mutating: `add_providers` invalidates the registry, clearing `is_validated`.
        recheck = reg.is_validation_enabled() or reg.is_validated()
        reg.add_providers(*providers)
        if recheck:
            try:
                self._eager_validate()
            except Exception:
                added_types = [provider.bound_type for provider in providers if provider.bound_type]
                reg._remove_providers(*added_types)  # noqa: SLF001
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
        """Prepare the container now, instead of on first use.

        Optional: a constructed container prepares itself on the first :meth:`resolve` or
        on the first resolve through a child. Call this to fail fast at startup (it runs
        any deferred validation) and to reopen a closed container deliberately. Opening an
        already-open container is a no-op.
        """
        self._ensure_ready()

    def _ensure_ready(self) -> None:
        """Finish any deferred validation, then mark this container open."""
        reg = self.providers_registry
        if not reg.is_validated() and (reg.is_validation_enabled() or reg.has_pending_errors()):
            self._complete_validation()
        self.closed = False
        self._ever_opened = True

    def _prepare(self) -> None:
        """Implicit open from the resolve path: a not-open container prepares itself on first use.

        A container that has never been open self-heals silently. One that was genuinely opened
        before and has since been closed explicitly still raises here — :meth:`open` bypasses
        this check to reopen it deliberately.
        """
        with self._lock or contextlib.nullcontext():
            if self.closed:  # re-checked under the lock: another thread may have prepared already
                if self._ever_opened:
                    raise exceptions.ContainerClosedError(container_scope=self.scope)
                self._ensure_ready()

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
