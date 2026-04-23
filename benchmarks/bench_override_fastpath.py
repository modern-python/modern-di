# ruff: noqa: ANN001, ANN201, E402
"""Benchmark: fix #1 (override fast-path) + fix #3 (int provider IDs).

Scenarios:
  no_overrides  — production-like; fast-path skips the dict lookup entirely
  override_other — one override active on a different provider
  override_self  — override active on the resolved provider (short-circuit path)

Each scenario has an `optimized` variant (current code) and a `baseline` variant
(pre-fix behaviour, monkey-patched in).

Run:
    uv run pytest benchmarks/ --benchmark-only --no-cov -v
"""

import dataclasses

from modern_di import Container, Group, Scope, providers, types
from modern_di.providers.abstract import AbstractProvider


# ---------------------------------------------------------------------------
# Subject graph
# ---------------------------------------------------------------------------


@dataclasses.dataclass(kw_only=True, slots=True)
class Dep:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class Service:
    dep: Dep


class BenchGroup(Group):
    dep = providers.Factory(scope=Scope.APP, creator=Dep)
    svc = providers.Factory(scope=Scope.APP, creator=Service)


# ---------------------------------------------------------------------------
# Baseline resolve_provider (pre-fix behaviour — always calls fetch_override)
# ---------------------------------------------------------------------------


def _baseline_resolve_provider(self: Container, provider: AbstractProvider) -> object:
    if (override := self.overrides_registry.fetch_override(provider.provider_id)) is not types.UNSET:
        return override
    return provider.resolve(self)


# ---------------------------------------------------------------------------
# Scenario 1 — no overrides active (production-like)
# ---------------------------------------------------------------------------


def test_no_overrides_optimized(benchmark):
    container = Container(scope=Scope.APP, groups=[BenchGroup])
    benchmark(container.resolve_provider, BenchGroup.svc)


def test_no_overrides_baseline(benchmark):
    original = Container.resolve_provider
    Container.resolve_provider = _baseline_resolve_provider  # ty: ignore[invalid-assignment]
    try:
        container = Container(scope=Scope.APP, groups=[BenchGroup])
        benchmark(container.resolve_provider, BenchGroup.svc)
    finally:
        Container.resolve_provider = original


# ---------------------------------------------------------------------------
# Scenario 2 — one override active on a *different* provider
# ---------------------------------------------------------------------------


def test_override_other_optimized(benchmark):
    container = Container(scope=Scope.APP, groups=[BenchGroup])
    container.override(BenchGroup.dep, Dep())
    benchmark(container.resolve_provider, BenchGroup.svc)


def test_override_other_baseline(benchmark):
    original = Container.resolve_provider
    Container.resolve_provider = _baseline_resolve_provider  # ty: ignore[invalid-assignment]
    try:
        container = Container(scope=Scope.APP, groups=[BenchGroup])
        container.override(BenchGroup.dep, Dep())
        benchmark(container.resolve_provider, BenchGroup.svc)
    finally:
        Container.resolve_provider = original


# ---------------------------------------------------------------------------
# Scenario 3 — override active on the *resolved* provider itself
# ---------------------------------------------------------------------------


def test_override_self_optimized(benchmark):
    container = Container(scope=Scope.APP, groups=[BenchGroup])
    container.override(BenchGroup.svc, Service(dep=Dep()))
    benchmark(container.resolve_provider, BenchGroup.svc)


def test_override_self_baseline(benchmark):
    original = Container.resolve_provider
    Container.resolve_provider = _baseline_resolve_provider  # ty: ignore[invalid-assignment]
    try:
        container = Container(scope=Scope.APP, groups=[BenchGroup])
        container.override(BenchGroup.svc, Service(dep=Dep()))
        benchmark(container.resolve_provider, BenchGroup.svc)
    finally:
        Container.resolve_provider = original


# ---------------------------------------------------------------------------
# Fix #3 micro-benchmark — int vs UUID string dict lookup in isolation
# ---------------------------------------------------------------------------

import uuid


_UUID_KEY = str(uuid.uuid4())
_INT_KEY = 0
_SENTINEL = object()


def test_dict_lookup_int_key(benchmark):
    """Cost of dict.get() with an integer key (fix #3 — current code)."""
    d: dict[int, object] = {}
    benchmark(d.get, _INT_KEY, _SENTINEL)


def test_dict_lookup_uuid_key(benchmark):
    """Cost of dict.get() with a UUID string key (pre-fix #3 baseline)."""
    d: dict[str, object] = {}
    benchmark(d.get, _UUID_KEY, _SENTINEL)


def test_dict_setdefault_int_key(benchmark):
    """Cost of dict.setdefault() with an integer key (cache_registry hot path)."""
    d: dict[int, object] = {}
    val = object()
    benchmark(d.setdefault, _INT_KEY, val)


def test_dict_setdefault_uuid_key(benchmark):
    """Cost of dict.setdefault() with a UUID string key (pre-fix #3 baseline)."""
    d: dict[str, object] = {}
    val = object()
    benchmark(d.setdefault, _UUID_KEY, val)
