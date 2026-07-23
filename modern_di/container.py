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
        "_lock",
        "_scope_map",
        "_validate_enabled",
        "_validated",
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

        A container starts **unopened** (``closed=True``): it must be entered via
        :meth:`open` / ``with`` / ``async with`` before it can :meth:`resolve` or
        :meth:`build_child_container`; using it before then raises
        :class:`~modern_di.exceptions.ContainerClosedError`.

        ``validate`` (default ``True``) enables the provider-graph check (cycles,
        scope ordering, missing dependencies), which runs **once at open()** —
        never in ``__init__`` and never on resolve. Deferring to ``open`` lets a
        framework integration register its context providers after construction
        and still have the complete graph validated. ``validate=False`` disables
        the check entirely; call :meth:`validate` explicitly for a
        construction-time check. Only a root container validates; children (with
        ``parent_container`` set) never do. ``context`` seeds this container's
        context registry. A root container owns fresh registries; a child shares
        the parent's providers/overrides registries and inherits its scope map.
        """
        if not isinstance(scope, enum.IntEnum):
            raise exceptions.InvalidScopeTypeError(scope_value=scope)
        if parent_container is not None and scope <= parent_container.scope:
            raise exceptions.InvalidChildScopeError(parent_scope=parent_container.scope, child_scope=scope)
        self._lock = threading.RLock() if use_lock else None
        self._validated = False
        self.closed = True  # unopened: enter via open()/with before resolving or building children
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
        # Root-only, run at open(): validation runs once when the container is entered, so an
        # integration's context providers registered after construction are in the graph before it
        # runs. False disables. Construction-time = call validate() explicitly.
        self._validate_enabled = validate and parent_container is None

    def build_child_container(
        self,
        *,
        scope: enum.IntEnum | None = None,
        context: dict[type[typing.Any], typing.Any] | None = None,
    ) -> "typing_extensions.Self":
        self._raise_if_closed()

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
        self._raise_if_closed()
        try:
            return self.providers_registry.resolver_for(provider)(self)
        except RecursionError as exc:
            _handle_recursion_error(provider, self, exc)

    def validate(self) -> None:
        reg = self.providers_registry
        if reg.is_validated():
            self._validated = True
            return  # already validated at this registry state — no re-walk

        validation_errors: list[Exception] = []
        graph = DependencyGraph()
        for event in graph.walk(reg, self):
            # Event is a closed 4-variant union — every variant handled below.
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
        reg.mark_validated()

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
        """Open the container so it can resolve and build children.

        Mandatory: a freshly-constructed container starts unopened and must be
        opened (here, or via ``with``/``async with`` which call this) before any
        :meth:`resolve` or :meth:`build_child_container`. Also reopens a closed
        container on re-entry. Use it directly when a callback-style lifecycle
        (e.g. a startup hook) cannot wrap the container in a ``with`` block.
        Opening an already-open container is a no-op.

        If validation is enabled (``validate`` was not ``False``; root only) and
        has not yet run, it runs here — once; a plain close/reopen does not
        re-walk the graph.
        """
        self.closed = False
        if self._validate_enabled and not self._validated:
            self.validate()

    def _raise_if_closed(self) -> None:
        """Raise if this container is closed; callers reopen explicitly via `open()`/`with`."""
        if self.closed:
            raise exceptions.ContainerClosedError(container_scope=self.scope)

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
