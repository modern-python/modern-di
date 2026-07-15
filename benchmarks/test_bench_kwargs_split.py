# ruff: noqa: ANN001, ANN201, ANN202, PERF403, SLF001
"""Benchmark: fix #4 — pre-split provider vs static kwargs at compile time.

Before: every resolve() call runs isinstance(v, AbstractProvider) for each kwarg.
After:  compile once into provider_kwargs + static_kwargs; resolve() just iterates.

Measured on a 3-level dependency chain (Step → Dep → Leaf) so the kwargs loop
runs multiple times per top-level resolve and the difference accumulates.

Run:
    just bench
"""

import dataclasses
import typing

from modern_di import Container, Group, Scope, providers
from modern_di.providers.abstract import AbstractProvider
from modern_di.wiring import WiringPlan


# ---------------------------------------------------------------------------
# Subject graph — 3-level chain so kwargs loop runs 3x per resolve()
# ---------------------------------------------------------------------------


@dataclasses.dataclass(kw_only=True, slots=True)
class Leaf:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class Dep:
    leaf: Leaf


@dataclasses.dataclass(kw_only=True, slots=True)
class Service:
    dep: Dep
    tag: str  # static kwarg — exercises the isinstance branch for non-providers too


class BenchGroup(Group):
    leaf = providers.Factory(scope=Scope.APP, creator=Leaf)
    dep = providers.Factory(scope=Scope.APP, creator=Dep)
    svc = providers.Factory(scope=Scope.APP, creator=Service, kwargs={"tag": "bench"})


# ---------------------------------------------------------------------------
# Baseline resolve() hot path — pre-fix #4: unified isinstance loop every call
# ---------------------------------------------------------------------------


def _baseline_resolve_inner(plan: WiringPlan, container: Container) -> dict[str, typing.Any]:
    """Simulate the old resolved_kwargs dict-comp that ran on every resolve()."""
    unified = {**plan.provider_kwargs, **plan.static_kwargs}
    return {k: container.resolve_provider(v) if isinstance(v, AbstractProvider) else v for k, v in unified.items()}


# ---------------------------------------------------------------------------
# Scenario A — uncached factory (new instance every call)
# ---------------------------------------------------------------------------


def test_uncached_optimized(benchmark):
    """Current code: split kwargs iterated separately, no isinstance at resolve time."""
    container = Container(scope=Scope.APP, groups=[BenchGroup])
    benchmark(container.resolve_provider, BenchGroup.svc)


def test_uncached_baseline(benchmark):
    """Baseline: unified dict-comp with isinstance on every resolve()."""
    container = Container(scope=Scope.APP, groups=[BenchGroup])
    # Warm up compilation so the plan is memoized (same as optimized path)
    container.resolve_provider(BenchGroup.svc)

    svc_provider = BenchGroup.svc

    def _baseline():
        # replicate what resolve() did before fix #4
        c = container.find_container(svc_provider.scope)
        resolved = _baseline_resolve_inner(svc_provider._plan(c), c)
        return svc_provider._creator(**resolved)

    benchmark(_baseline)


# ---------------------------------------------------------------------------
# Scenario B — singleton (cached instance, kwargs loop still runs)
# ---------------------------------------------------------------------------


def test_singleton_optimized(benchmark):
    """Cached provider: current code resolves deps via split dicts."""

    class SGroup(Group):
        leaf = providers.Factory(scope=Scope.APP, creator=Leaf, cache=True)
        dep = providers.Factory(scope=Scope.APP, creator=Dep, cache=True)
        svc = providers.Factory(scope=Scope.APP, creator=Service, kwargs={"tag": "bench"}, cache=True)

    container = Container(scope=Scope.APP, groups=[SGroup])
    container.resolve_provider(SGroup.svc)  # warm cache
    benchmark(container.resolve_provider, SGroup.svc)


def test_singleton_baseline(benchmark):
    """Cached provider: baseline unified dict-comp with isinstance."""

    class SGroup(Group):
        leaf = providers.Factory(scope=Scope.APP, creator=Leaf, cache=True)
        dep = providers.Factory(scope=Scope.APP, creator=Dep, cache=True)
        svc = providers.Factory(scope=Scope.APP, creator=Service, kwargs={"tag": "bench"}, cache=True)

    container = Container(scope=Scope.APP, groups=[SGroup])
    container.resolve_provider(SGroup.svc)  # warm cache

    svc_provider = SGroup.svc
    cache_item = container.cache_registry.fetch_cache_item(svc_provider)

    def _baseline():
        c = container.find_container(svc_provider.scope)
        # resolve the unified kwargs (even though cache exists — mimics pre-fix path)
        _baseline_resolve_inner(svc_provider._plan(c), c)
        # return cached instance (same as current code does after kwargs loop)
        return cache_item.cache

    benchmark(_baseline)


# ---------------------------------------------------------------------------
# Micro-benchmark — isolated kwargs loop cost (no provider.resolve overhead)
# ---------------------------------------------------------------------------

_STATIC = {"a": 1, "b": "hello", "c": 3.14}
_RESOLVED = object()


def test_kwargs_loop_split(benchmark):
    """Cost of: copy statics + iterate providers (0 providers, 3 statics)."""
    provider_kwargs: dict[str, object] = {}
    static_kwargs = _STATIC

    def _loop():
        resolved: dict[str, object] = dict(static_kwargs)
        for k, v in provider_kwargs.items():
            resolved[k] = v
        return resolved

    benchmark(_loop)


def test_kwargs_loop_unified(benchmark):
    """Cost of: unified isinstance dict-comp (0 providers, 3 statics)."""
    unified = {**_STATIC}

    def _loop():
        return {k: _RESOLVED if isinstance(v, AbstractProvider) else v for k, v in unified.items()}

    benchmark(_loop)
