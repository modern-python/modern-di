import enum
import os
import pathlib
import sys
import threading
import typing
import warnings
from types import FrameType

from modern_di import exceptions, types
from modern_di.dependency_graph import (
    Cycle,
    DependenciesError,
    DependencyGraph,
    Edge,
    NodeEntered,
    build_cycle_error,
    effective_scope,
    terminal_chain,
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

    A separate call, not inlined into `resolve_provider`: the coverage tracer re-arms on the
    fresh call boundary before this raises.
    """
    reg = container.providers_registry
    if reg.is_validated():
        raise exc  # validated => acyclic static graph => genuine self-recursion
    cycle = DependencyGraph().find_cycle_from(provider, container)
    if cycle is None:
        raise exc
    raise build_cycle_error(cycle, container) from exc


# Trailing separator: without it the prefix test also swallows `modern_di_fastapi/` and friends.
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

    A root is built as ``Container(scope=Scope.APP, groups=[...])``; children come from
    :meth:`build_child_container` and share the parent's providers and overrides registries
    while owning their own cache and context.
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
        """Build a container at ``scope``, open and ready to :meth:`resolve`.

        ``context`` seeds the context registry. A root binds :class:`Container` itself, so
        ``resolve(Container)`` returns the resolving container. ``validate`` is deprecated and
        ignored: passing it emits
        :class:`~modern_di.exceptions.ValidateArgumentWarning` and changes nothing.

        Raises :class:`~modern_di.exceptions.InvalidScopeTypeError` when ``scope`` is not an
        ``IntEnum``, and :class:`~modern_di.exceptions.InvalidChildScopeError` when it is not
        deeper than ``parent_container``'s.
        """
        if validate is not None:
            warnings.warn(exceptions.ValidateArgumentWarning(), stacklevel=2)
        if not isinstance(scope, enum.IntEnum):
            raise exceptions.InvalidScopeTypeError(scope_value=scope)
        if parent_container is not None and scope <= parent_container.scope:
            raise exceptions.InvalidChildScopeError(parent_scope=parent_container.scope, child_scope=scope)
        self._lock = (
            parent_container._lock  # noqa: SLF001
            if parent_container is not None
            else (threading.RLock() if use_lock else None)
        )
        self.closed = False
        self.scope = scope
        self.parent_container = parent_container
        # Ancestors only, never self: a `scope: self` entry is a reference cycle, so no container
        # would ever be freed by refcounting.
        self._scope_map: dict[enum.IntEnum, typing_extensions.Self] = (
            {**parent_container._scope_map, parent_container.scope: parent_container}  # noqa: SLF001
            if parent_container
            else {}
        )
        self.cache_registry = CacheRegistry()
        self.context_registry = ContextRegistry(context=context or {})
        self.providers_registry: ProvidersRegistry
        self.overrides_registry: OverridesRegistry
        # Inlined rather than a helper: this runs per child build (benchmark `test_g6_build_child_container`).
        if parent_container:
            self.providers_registry = parent_container.providers_registry
            self.overrides_registry = parent_container.overrides_registry
        else:
            self.providers_registry = ProvidersRegistry()
            self.providers_registry.register(Container, container_provider)
            self.overrides_registry = self.providers_registry.overrides
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
            scope = _next_deeper(self.scope)
            if scope is None:
                raise exceptions.MaxScopeReachedError(parent_scope=self.scope)

        return self.__class__(scope=scope, parent_container=self, context=context)

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
        registry = self.providers_registry
        try:
            resolver = registry._resolvers_by_type.get(dependency_type)  # noqa: SLF001
            if resolver is None:
                resolver = registry.resolver_for_type(dependency_type)
            if self.closed:
                self._prepare()
            return resolver(self)
        except RecursionError as exc:
            _handle_recursion_error(registry._providers[dependency_type], self, exc)  # noqa: SLF001

    def resolve_dependency(self, dependency: "AbstractProvider[types.T] | type[types.T]") -> types.T:
        """Resolve a provider reference via :meth:`resolve_provider`, or a type via :meth:`resolve`."""
        if isinstance(dependency, AbstractProvider):
            return self.resolve_provider(dependency)
        return self.resolve(dependency)

    def resolve_provider(self, provider: "AbstractProvider[types.T]") -> types.T:
        """Resolve a specific provider by reference via its compiled resolver."""
        if self.closed:
            self._prepare()
        try:
            registry = self.providers_registry
            resolver = registry._resolvers.get(provider.provider_id)  # noqa: SLF001
            if resolver is None:
                resolver = registry.resolver_for(provider)
            return resolver(self)
        except RecursionError as exc:
            _handle_recursion_error(provider, self, exc)

    def _walk_errors(self) -> list[Exception]:
        """Walk the graph once, returning every wiring error in walk order."""
        errors: list[Exception] = []
        graph = DependencyGraph()
        for event in graph.walk(self.providers_registry, self):
            match event:
                case NodeEntered(provider):
                    errors.extend(provider.iter_validation_issues(self))
                case DependenciesError(_, error):
                    errors.append(error)
                case Edge(parent, name, dep):
                    dep_chain = terminal_chain(dep, self)
                    if dep_chain[-1].scope > effective_scope(parent, self):
                        errors.append(
                            exceptions.InvalidScopeDependencyError(
                                provider=parent,
                                parameter_name=name,
                                dep_chain=dep_chain,
                            )
                        )
                case Cycle(providers):
                    errors.append(build_cycle_error(providers, self))
        return errors

    def validate(self) -> None:
        """Walk the static provider graph and raise on any wiring error.

        Checks cycles, transitive scope ordering and unresolvable dependencies, aggregating every
        error into one :class:`~modern_di.exceptions.ValidationFailedError`. The only thing that
        validates — construction, :meth:`open`, :meth:`add_providers` and :meth:`resolve` never
        do. A clean walk is memoized until the registry changes.
        """
        reg = self.providers_registry
        if reg.is_validated():
            return

        validation_errors = self._walk_errors()
        if validation_errors:
            raise exceptions.ValidationFailedError(errors=validation_errors)
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
        """Apply an override immediately, tree-wide.

        Use the returned handle as a context manager to restore the prior state. A test-time
        operation, not coordinated with concurrent resolves on other threads.
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

        Context never propagates between parent and child — set it on the container whose scope
        matches the ``ContextProvider``. A cached provider is built once and is not rebuilt by a
        later ``set_context``; set the context before its first resolve.
        """
        self.context_registry.set_context(context_type, obj)

    def __repr__(self) -> str:
        n_providers = len(self.providers_registry)
        n_cached = self.cache_registry.cached_count()
        parent = self.parent_container.scope.name if self.parent_container else None
        return f"Container(scope={self.scope.name}, parent={parent}, providers={n_providers}, cached={n_cached})"

    def open(self) -> None:
        """Reopen a closed container silently; a no-op on an open one, and never validates.

        Optional: a constructed container is already open, and an implicit reuse reopens too,
        with a warning.
        """
        self.closed = False

    def _prepare(self) -> None:
        """Reopen a closed container on implicit reuse, warning the caller. Callers guard on ``closed``."""
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
