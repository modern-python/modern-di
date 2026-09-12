import threading
import typing

from modern_di import exceptions, suggester, types
from modern_di.providers.abstract import AbstractProvider
from modern_di.registries.overrides_registry import OverridesRegistry
from modern_di.resolver_compiler import compile_resolver
from modern_di.wiring import WiringPlan


if typing.TYPE_CHECKING:
    from modern_di import Container
    from modern_di.providers.factory import Factory
    from modern_di.types_parser import SignatureItem


class ProvidersRegistry:
    __slots__ = (
        "_building",
        "_generation",
        "_lock",
        "_plans",
        "_providers",
        "_resolvers",
        "_resolvers_by_type",
        "_validated",
        "overrides",
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._providers: dict[type, AbstractProvider[typing.Any]] = {}
        self._plans: dict[int, WiringPlan] = {}
        self._resolvers: dict[int, typing.Callable[[Container], typing.Any]] = {}
        self._resolvers_by_type: dict[type, typing.Callable[[Container], typing.Any]] = {}
        self.overrides = OverridesRegistry(on_change=self.drop_resolvers)
        self._building = threading.local()
        self._validated = False
        self._generation = 0

    def __len__(self) -> int:
        return len(self._providers)

    def __iter__(self) -> typing.Iterator[AbstractProvider[typing.Any]]:
        return iter(list(self._providers.values()))

    def is_validated(self) -> bool:
        """Return whether the graph was validated with no registry mutation since."""
        return self._validated

    def mark_validated(self) -> None:
        """Mark the graph validated; any later mutation clears this."""
        self._validated = True

    def find_provider(self, dependency_type: type[types.T]) -> AbstractProvider[types.T] | None:
        return self._providers.get(dependency_type)

    def plan_for(
        self,
        provider: "Factory[typing.Any]",
        parsed_kwargs: "dict[str, SignatureItem]",
        kwargs: dict[str, typing.Any] | None,
    ) -> "WiringPlan":
        """Return `provider`'s memoized wiring plan, building it on a miss.

        The memo is tree-wide and dropped on every registry mutation.
        """
        provider_id = provider.provider_id
        cached = self._plans.get(provider_id)
        if cached is not None:
            return cached
        generation = self._generation
        plan = WiringPlan.build(parsed_kwargs=parsed_kwargs, kwargs=kwargs, registry=self, owner=provider)
        with self._lock:
            if self._generation == generation:
                self._plans[provider_id] = plan
        return plan

    def _building_set(self) -> set[int]:
        """Return this thread's in-flight-compile set; per-thread, so a concurrent compile is not a cycle."""
        building: set[int] | None = getattr(self._building, "value", None)
        if building is None:
            building = set()
            self._building.value = building
        return building

    def resolver_for(self, provider: "AbstractProvider[typing.Any]") -> "typing.Callable[[Container], typing.Any]":
        """Return `provider`'s memoized compiled resolver, building it on a miss.

        A back-edge to a provider still being compiled captures a thunk routed through the
        runtime `resolve_provider`, so a genuine cycle still raises `CircularDependencyError`.
        """
        pid = provider.provider_id
        cached = self._resolvers.get(pid)
        if cached is not None:
            return cached
        building = self._building_set()
        if pid in building:
            return lambda c: c.resolve_provider(provider)
        building.add(pid)
        generation = self._generation
        try:
            resolver = compile_resolver(provider, self)
        finally:
            building.discard(pid)
        with self._lock:
            # Publish only if no mutation landed while we compiled; memoizing a resolver built
            # against the old registry would strand it past the `_invalidate()` meant to drop it.
            if self._generation == generation:
                self._resolvers[pid] = resolver
        return resolver

    def resolver_for_type(self, dependency_type: type) -> "typing.Callable[[Container], typing.Any]":
        """Return the resolver bound to `dependency_type`; raises `ProviderNotRegisteredError` when unbound."""
        generation = self._generation
        provider = self._providers.get(dependency_type)
        if provider is None:
            raise exceptions.ProviderNotRegisteredError(
                provider_type=dependency_type, suggestions=suggester.suggest(dependency_type, self)
            )
        resolver = self.resolver_for(provider)
        with self._lock:
            if self._generation == generation:
                self._resolvers_by_type[dependency_type] = resolver
        return resolver

    def drop_resolvers(self) -> None:
        """Drop the compiled resolvers — the overrides changed. Plans and the validation flag survive."""
        with self._lock:
            self._resolvers.clear()
            self._resolvers_by_type.clear()
            self._generation += 1

    def register(self, provider_type: type, provider: AbstractProvider[typing.Any]) -> None:
        with self._lock:
            if provider_type in self._providers:
                raise exceptions.DuplicateProviderTypeError(provider_type=provider_type)
            self._providers[provider_type] = provider
            provider._registered = True  # noqa: SLF001
            self._invalidate()

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
            # Over `args`, not `new_providers`: a reference-only provider never enters
            # `_providers`, but its resolver is still compiled and still captures its scope.
            for provider in args:
                provider._registered = True  # noqa: SLF001
            self._invalidate()

    def _invalidate(self) -> None:
        """Drop every memo and the validation flag — the registry changed. Called under `self._lock`."""
        self._plans.clear()
        self._resolvers.clear()
        self._resolvers_by_type.clear()
        self._validated = False
        self._generation += 1
