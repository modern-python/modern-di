import enum
import os
import pathlib
import sys
import threading
import typing
import warnings
from types import FrameType

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


# Trailing separator included: without it the prefix test also swallows sibling packages
# (`modern_di_fastapi/`, `modern_di_pytest/`, ...), attributing a warning past the integration.
_PACKAGE_DIR = str(pathlib.Path(__file__).parent) + os.sep


def _caller_stacklevel() -> int:
    """Frames to skip so a warning points at the caller, not at modern_di internals."""
    level = 1
    frame: FrameType | None = sys._getframe(1)  # noqa: SLF001
    while frame is not None and frame.f_code.co_filename.startswith(_PACKAGE_DIR):
        level += 1
        frame = frame.f_back
    return level


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
        validate: bool | None = None,
    ) -> None:
        """Build a container at ``scope``.

        A container is open from construction — no separate startup step is required
        before the first :meth:`resolve`. :meth:`open` and ``with`` / ``async with``
        stay available for reopening a closed container deliberately and for running
        finalizers on the way out.

        ``validate`` is ignored and deprecated: passing it (either value) emits
        :class:`~modern_di.exceptions.ValidateArgumentWarning` and changes nothing.
        Graph validation (cycles, scope ordering, missing dependencies) runs only
        when :meth:`validate` is called explicitly — construction, ``open()``, and
        ``resolve()`` never trigger it. ``context`` seeds this container's context
        registry. A root container owns fresh registries; a child shares the
        parent's providers/overrides registries and inherits its scope map.
        """
        if validate is not None:
            warnings.warn(exceptions.ValidateArgumentWarning(), stacklevel=2)
        if not isinstance(scope, enum.IntEnum):
            raise exceptions.InvalidScopeTypeError(scope_value=scope)
        if parent_container is not None and scope <= parent_container.scope:
            raise exceptions.InvalidChildScopeError(parent_scope=parent_container.scope, child_scope=scope)
        self._lock = threading.RLock() if use_lock else None
        self.closed = False
        self.scope = scope
        self.parent_container = parent_container
        # Ancestors only, never self: a `scope: self` entry would make every container a reference
        # cycle, so none could be freed by refcounting. `find_container` short-circuits on its own
        # scope before consulting this map, so the self-entry was never read anyway.
        self._scope_map: dict[enum.IntEnum, typing_extensions.Self] = (
            {**parent_container._scope_map, parent_container.scope: parent_container}  # noqa: SLF001
            if parent_container
            else {}
        )
        self.cache_registry = CacheRegistry()
        self.context_registry = ContextRegistry(context=context or {})
        self.providers_registry: ProvidersRegistry
        self.overrides_registry: OverridesRegistry
        # Inlined, not a helper: __init__ is on the per-request child-build path
        # (architecture/performance.md). A root seeds container_provider so `Container`
        # resolves to the resolving container.
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
        """Resolve a dependency by its type.

        Carries its own copy of `resolve_provider`'s body rather than calling it: the extra
        frame is ~19% of a by-type resolve. The duplication is deliberate and the two must be
        edited together -- see planning/decisions/2026-08-03-resolve-provider-not-a-seam.md.
        """
        registry = self.providers_registry
        provider = registry._providers.get(dependency_type)  # noqa: SLF001
        if provider is None:
            raise exceptions.ProviderNotRegisteredError(
                provider_type=dependency_type,
                suggestions=suggester.suggest(dependency_type, registry),
            )
        if self.closed:
            self._prepare()
        try:
            resolver = registry._resolvers.get(provider.provider_id)  # noqa: SLF001
            if resolver is None:
                resolver = registry.resolver_for(provider)
            return resolver(self)
        except RecursionError as exc:
            _handle_recursion_error(provider, self, exc)

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
        """Resolve a specific provider by reference via its compiled resolver.

        `resolve` holds a copy of this body; any change here belongs there too.
        """
        if self.closed:
            self._prepare()
        try:
            # Inlined memo hit; `resolver_for` is called only on a miss, where it owns the cycle
            # guard and the memo write (architecture/performance.md). Inside the try so a
            # RecursionError while compiling still becomes CircularDependencyError.
            registry = self.providers_registry
            resolver = registry._resolvers.get(provider.provider_id)  # noqa: SLF001
            if resolver is None:
                resolver = registry.resolver_for(provider)
            return resolver(self)
        except RecursionError as exc:
            # `resolve` carries its own copy of this call, so below 3.12 -- where coverage traces
            # instead of using `sys.monitoring` -- this one is reached only by a by-reference
            # cycle, and the RecursionError tears the tracer down before the line is recorded.
            # It does execute: `test_by_reference_cycle_raises_circular_dependency_error` fails
            # without it, and coverage records it when tracing this module alone.
            _handle_recursion_error(provider, self, exc)  # pragma: no cover

    def _walk_errors(self) -> list[Exception]:
        """Walk the graph once, returning every wiring error in walk order."""
        errors: list[Exception] = []
        graph = DependencyGraph()
        for event in graph.walk(self.providers_registry, self):
            # Event is a closed 4-variant union — every variant handled below.
            match event:
                case NodeEntered(provider):
                    errors.extend(provider.iter_validation_issues(self))
                case DependenciesError(_, error):
                    errors.append(error)
                case Edge(parent, name, dep):
                    dep_scope = graph.terminal_scope(dep, self)
                    if dep_scope > graph.terminal_scope(parent, self):
                        errors.append(
                            exceptions.InvalidScopeDependencyError(
                                provider=parent,
                                parameter_name=name,
                                dep_provider=dep,
                                dep_scope=dep_scope,
                            )
                        )
                case Cycle(providers):
                    errors.append(build_cycle_error(providers))
        return errors

    def validate(self) -> None:
        """Walk the static provider graph and raise on any wiring error.

        Checks cycles, transitive scope ordering, and missing/unresolvable dependencies;
        every error found is aggregated into a single :class:`~modern_di.exceptions.ValidationFailedError`
        rather than raising on the first one. This is the only thing that validates —
        construction, :meth:`open`, ``add_providers``, and ``resolve`` never do.
        """
        reg = self.providers_registry
        if reg.is_validated():
            return  # already validated at this registry state — no re-walk

        validation_errors = self._walk_errors()
        if validation_errors:
            raise exceptions.ValidationFailedError(errors=validation_errors)
        reg.mark_validated()

    def add_providers(self, *providers: AbstractProvider[typing.Any]) -> None:
        """Register providers on this (root) container after construction.

        The blessed seam for framework integrations that discover providers after the
        container is built. Root-only: on a child this raises
        :class:`~modern_di.exceptions.ChildContainerRegistrationError`, since the registry
        it mutates is shared tree-wide. Registration does not validate; the mutation clears
        the registry's validated flag, so a later :meth:`validate` re-walks the new graph.
        Registration is a startup-time operation: concurrent calls on the same root are not
        coordinated beyond the registry's internal lock.
        """
        if self.parent_container is not None:
            raise exceptions.ChildContainerRegistrationError(scope=self.scope)
        self.providers_registry.add_providers(*providers)

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
        """Open the container, silently.

        Optional: a constructed container is already open. Use it to reopen a closed
        container deliberately — an implicit reuse reopens too, but warns. Opening an
        open container is a no-op. Validation is not run here; call :meth:`validate`.
        """
        self.closed = False

    def _prepare(self) -> None:
        """Reopen a closed container on implicit reuse, warning the caller.

        Callers guard with ``if closed``. Unlocked: threads racing a closed container
        may each warn, but every one of them writes the same ``closed = False``.
        """
        warnings.warn(
            exceptions.ContainerClosedWarning(container_scope=self.scope),
            stacklevel=_caller_stacklevel(),
        )
        self.closed = False

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

    def __copy__(self, *_: object, **__: object) -> "typing_extensions.Self":
        """Never clone: a copied container would own a detached cache whose finalizers never run."""
        return self

    __deepcopy__ = __copy__
