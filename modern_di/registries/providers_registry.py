import threading
import typing

from modern_di import exceptions, types
from modern_di.providers.abstract import AbstractProvider
from modern_di.wiring import WiringPlan


if typing.TYPE_CHECKING:
    from modern_di.types_parser import SignatureItem


class ProvidersRegistry:
    __slots__ = ("_lock", "_plans", "_providers", "_version", "validated_version")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._providers: dict[type, AbstractProvider[typing.Any]] = {}
        self._plans: dict[int, tuple[int, WiringPlan]] = {}
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

    def find_provider(self, dependency_type: type[types.T]) -> AbstractProvider[types.T] | None:
        return self._providers.get(dependency_type)

    def plan_for(
        self,
        provider: AbstractProvider[typing.Any],
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
        # provider is AbstractProvider here (this registry's generic contract), but the sole caller
        # (Factory._plan) only ever passes a Factory, matching WiringPlan.build's owner: Factory bound.
        plan = WiringPlan.build(
            parsed_kwargs=parsed_kwargs,
            kwargs=kwargs,
            registry=self,
            owner=provider,  # ty: ignore[invalid-argument-type]
        )
        self._plans[provider_id] = (version, plan)
        return plan

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
