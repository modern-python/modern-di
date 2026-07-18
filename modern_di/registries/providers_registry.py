import threading
import typing

from modern_di import exceptions, types
from modern_di.providers.abstract import AbstractProvider
from modern_di.resolver_compiler import compile_resolver
from modern_di.wiring import WiringPlan


if typing.TYPE_CHECKING:
    from modern_di import Container
    from modern_di.providers.factory import Factory
    from modern_di.types_parser import SignatureItem


class ProvidersRegistry:
    __slots__ = ("_building", "_lock", "_plans", "_providers", "_resolvers", "_version", "validated_version")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._providers: dict[type, AbstractProvider[typing.Any]] = {}
        self._plans: dict[int, tuple[int, WiringPlan]] = {}
        self._resolvers: dict[int, tuple[int, typing.Callable[[Container], typing.Any]]] = {}
        self._building = threading.local()  # per-thread compile-in-flight set; the cycle guard is per-call-stack
        self._version = 0
        self.validated_version: int | None = None

    def __len__(self) -> int:
        return len(self._providers)

    def __iter__(self) -> typing.Iterator[AbstractProvider[typing.Any]]:
        return iter(list(self._providers.values()))

    @property
    def version(self) -> int:
        """Monotonically increasing counter, bumped on every mutation.

        Stamps the memoized `WiringPlan`s held in `_plans` (see `plan_for`) so a plan built
        against an older registry is rebuilt instead of resolving against a stale one.
        """
        return self._version

    def is_validated(self) -> bool:
        """Return whether the graph was validated at the current version — no mutation since the stamp."""
        return self.validated_version == self._version

    def mark_validated(self) -> None:
        """Stamp the current version as validated; a later mutation re-arms it via the version bump."""
        self.validated_version = self._version

    def find_provider(self, dependency_type: type[types.T]) -> AbstractProvider[types.T] | None:
        return self._providers.get(dependency_type)

    def plan_for(
        self,
        provider: "Factory[typing.Any]",
        parsed_kwargs: "dict[str, SignatureItem]",
        kwargs: dict[str, typing.Any] | None,
    ) -> "WiringPlan":
        """Return `provider`'s memoized wiring plan, building and stamping it on a miss.

        A plan is a pure function of the provider and this registry's contents, so it is
        memoized per `provider_id` and stamped with the `version` it was built against; a
        stamp mismatch (the registry mutated since) rebuilds. The version is snapshotted
        *before* the build runs, so a plan built against a since-mutated registry carries the
        old stamp and is never served as current. Shared tree-wide: a container and every
        child share one registry, so a deeper-scope provider builds its plan once, not once
        per child container. The build inputs are passed by value (not a closure) so the hot
        cache-hit path allocates nothing.
        """
        provider_id = provider.provider_id
        version = self._version
        cached = self._plans.get(provider_id)
        if cached is not None and cached[0] == version:
            return cached[1]
        plan = WiringPlan.build(parsed_kwargs=parsed_kwargs, kwargs=kwargs, registry=self, owner=provider)
        self._plans[provider_id] = (version, plan)
        return plan

    def _building_set(self) -> set[int]:
        """Return the current thread's in-flight-compile set (the cycle guard).

        Per-call-stack: a concurrent first-resolve of the same provider on another thread compiles it
        independently (an idempotent duplicate) instead of being misread as a dependency cycle.
        """
        building: set[int] | None = getattr(self._building, "value", None)
        if building is None:
            building = set()
            self._building.value = building
        return building

    def resolver_for(self, provider: "AbstractProvider[typing.Any]") -> "typing.Callable[[Container], typing.Any]":
        """Return `provider`'s memoized compiled resolver, building it cycle-safely on a miss.

        Memoized and version-stamped exactly like `plan_for`. A back-edge to a provider whose
        resolver is still being built (a cycle) captures a thunk that routes through the runtime
        `resolve_provider`, so a genuine cycle still raises `RecursionError` -> `CircularDependencyError`.
        """
        pid = provider.provider_id
        version = self._version
        cached = self._resolvers.get(pid)
        if cached is not None and cached[0] == version:
            return cached[1]
        building = self._building_set()
        if pid in building:
            return lambda c: c.resolve_provider(provider)  # back-edge: route the cycle through runtime
        building.add(pid)
        try:
            resolver = compile_resolver(provider, self)
        finally:
            building.discard(pid)
        self._resolvers[pid] = (version, resolver)
        return resolver

    def register(self, provider_type: type, provider: AbstractProvider[typing.Any]) -> None:
        with self._lock:
            if provider_type in self._providers:
                raise exceptions.DuplicateProviderTypeError(provider_type=provider_type)
            self._providers[provider_type] = provider
            self._version += 1
            self.validated_version = None

    def add_providers(self, *args: AbstractProvider[typing.Any]) -> None:
        new_providers: dict[type, AbstractProvider[typing.Any]] = {}
        for provider in args:
            if not provider.bound_type:
                continue
            if provider.bound_type in new_providers:
                raise exceptions.DuplicateProviderTypeError(provider_type=provider.bound_type)
            new_providers[provider.bound_type] = provider

        with self._lock:
            for provider_type in new_providers:
                if provider_type in self._providers:
                    raise exceptions.DuplicateProviderTypeError(provider_type=provider_type)
            self._providers.update(new_providers)
            self._version += 1
            self.validated_version = None

    def _remove_providers(self, *provider_types: type) -> None:
        """Rollback helper for `Container.add_providers`; not part of the public API."""
        with self._lock:
            for provider_type in provider_types:
                self._providers.pop(provider_type, None)
            self._version += 1
            self.validated_version = None
