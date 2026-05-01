# ruff: noqa: ANN001, ANN201, E402
"""Benchmark: cycle detection overhead in resolve_provider.

Compares current code (with threading.local cycle tracking) against
baseline (no cycle detection).

Run:
    uv run pytest benchmarks/bench_cycle_detection.py --benchmark-only --no-cov -v
"""

import dataclasses
import typing

from modern_di import Container, Group, Scope, providers, types
from modern_di.providers.abstract import AbstractProvider


@dataclasses.dataclass(kw_only=True, slots=True)
class DepA:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class DepB:
    a: DepA


@dataclasses.dataclass(kw_only=True, slots=True)
class DepC:
    b: DepB


class BenchGroup(Group):
    a = providers.Factory(scope=Scope.APP, creator=DepA)
    b = providers.Factory(scope=Scope.APP, creator=DepB)
    c = providers.Factory(scope=Scope.APP, creator=DepC)


# Baseline: no cycle detection (pre-fix behaviour)
def _baseline_resolve_provider(self: Container, provider: "AbstractProvider[types.T]") -> types.T:
    if (
        self.overrides_registry.overrides
        and (override := self.overrides_registry.fetch_override(provider.provider_id)) is not types.UNSET
    ):
        return override  # ty: ignore[invalid-return-type]
    return provider.resolve(self)


# --- Leaf resolution (no deps) ---

def test_leaf_optimized(benchmark):
    """Resolve a leaf provider (no dependencies) — with cycle detection."""
    container = Container(scope=Scope.APP, groups=[BenchGroup])
    benchmark(container.resolve_provider, BenchGroup.a)


def test_leaf_baseline(benchmark):
    """Resolve a leaf provider (no dependencies) — without cycle detection."""
    original = Container.resolve_provider
    Container.resolve_provider = _baseline_resolve_provider  # ty: ignore[invalid-assignment]
    try:
        container = Container(scope=Scope.APP, groups=[BenchGroup])
        benchmark(container.resolve_provider, BenchGroup.a)
    finally:
        Container.resolve_provider = original


# --- 2-level chain ---

def test_chain2_optimized(benchmark):
    """Resolve a 2-level dependency chain — with cycle detection."""
    container = Container(scope=Scope.APP, groups=[BenchGroup])
    benchmark(container.resolve_provider, BenchGroup.b)


def test_chain2_baseline(benchmark):
    """Resolve a 2-level dependency chain — without cycle detection."""
    original = Container.resolve_provider
    Container.resolve_provider = _baseline_resolve_provider  # ty: ignore[invalid-assignment]
    try:
        container = Container(scope=Scope.APP, groups=[BenchGroup])
        benchmark(container.resolve_provider, BenchGroup.b)
    finally:
        Container.resolve_provider = original


# --- 3-level chain ---

def test_chain3_optimized(benchmark):
    """Resolve a 3-level dependency chain — with cycle detection."""
    container = Container(scope=Scope.APP, groups=[BenchGroup])
    benchmark(container.resolve_provider, BenchGroup.c)


def test_chain3_baseline(benchmark):
    """Resolve a 3-level dependency chain — without cycle detection."""
    original = Container.resolve_provider
    Container.resolve_provider = _baseline_resolve_provider  # ty: ignore[invalid-assignment]
    try:
        container = Container(scope=Scope.APP, groups=[BenchGroup])
        benchmark(container.resolve_provider, BenchGroup.c)
    finally:
        Container.resolve_provider = original