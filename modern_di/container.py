import enum
import threading
import typing
import warnings

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
        at construction time. ``validate=False`` skips the check silently.
        Leaving ``validate`` unset (``None``, the default) skips the check but
        warns with :class:`~modern_di.exceptions.UnvalidatedContainerWarning` on
        a root container — modern-di 3.0 will run ``validate()`` by default;
        pass ``validate=True`` to adopt that now or ``validate=False`` to opt
        out silently. Child containers (with ``parent_container`` set) never
        warn regardless. ``context`` seeds this container's context registry.
        A root container owns fresh registries; a child shares the parent's
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
                "See https://modern-di.modern-python.org/migration/to-3.x/.",
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

    def resolve_provider(self, provider: "AbstractProvider[types.T]") -> types.T:
        """Resolve a specific provider by reference (enforces closed-state and applies overrides)."""
        self._warn_and_reopen_if_closed()

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
                cycle_names = [p.display_name for p in path[cycle_start:]]
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
        container).

        Context values are resolved live, so a value set here is picked up by
        subsequent resolves of **non-cached** providers — including factories in
        deeper-scoped child containers that read this container's context. A
        **cached** provider (``Factory(cache=...)``) is built once and
        its instance is *not* rebuilt by a later ``set_context``; set the context
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

        Emits :class:`~modern_di.exceptions.ContainerClosedWarning` and reopens
        (so pre-2.16 "close then resolve" code keeps working); modern-di 3.0
        will raise :class:`~modern_di.exceptions.ContainerClosedError` here
        instead. The warning fires once per container transitioning from closed
        to reopened — a single resolve that crosses several distinct closed
        containers (e.g. a closed ancestor scope) emits one warning per closed
        container it reopens; an already-open container emits none.
        """
        if not self.closed:
            return
        warnings.warn(
            f"Container (scope {self.scope.name}) is closed; resolving from it or building a child "
            "is deprecated and will raise ContainerClosedError in modern-di 3.0. Re-enter the "
            "container with `with`/`async with`, or call `open()`, before reusing it.",
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
