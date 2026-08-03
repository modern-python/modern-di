# ruff: noqa: ANN001, ANN201
"""Guard tier — cold first-resolve (container build + graph compile).

G8 is the **one** guard scenario that builds the root container *inside* the
timed call: a fresh `Container(groups=[...])` has a fresh providers registry, so
the first resolve compiles the whole provider graph from scratch. Every other
guard file builds/warms in setup and times only the steady-state call; this one
deliberately measures construction + compile + resolve as a single unit, the
cost paid once per container in short-lived processes (serverless, CLI, tests)
and at every app startup. See benchmarks/README.md.
"""

import dataclasses

from modern_di import Container, Group, Scope, providers


# --- depth-6 chain subject graph (mirrors G3/C3, the largest compile signal) ---
@dataclasses.dataclass(slots=True)
class C5:
    pass


@dataclasses.dataclass(slots=True)
class C4:
    c5: C5


@dataclasses.dataclass(slots=True)
class C3:
    c4: C4


@dataclasses.dataclass(slots=True)
class C2:
    c3: C3


@dataclasses.dataclass(slots=True)
class C1:
    c2: C2


@dataclasses.dataclass(slots=True)
class C0:
    c1: C1


class ChainGroup(Group):
    c5 = providers.Factory(creator=C5, scope=Scope.APP)
    c4 = providers.Factory(creator=C4, scope=Scope.APP)
    c3 = providers.Factory(creator=C3, scope=Scope.APP)
    c2 = providers.Factory(creator=C2, scope=Scope.APP)
    c1 = providers.Factory(creator=C1, scope=Scope.APP)
    c0 = providers.Factory(creator=C0, scope=Scope.APP)


def _cold_build_and_resolve() -> C0:
    # Fresh registry -> full compile every call: construction + open + first-resolve compile + resolve.
    container = Container(scope=Scope.APP, groups=[ChainGroup])
    container.open()
    return container.resolve_provider(ChainGroup.c0)


def test_g8_cold_first_resolve(benchmark):
    result = benchmark(_cold_build_and_resolve)
    assert isinstance(result, C0)
    assert isinstance(result.c1.c2.c3.c4.c5, C5)


# --- G8b: the same shape with caching on, so the cached cold-miss builders are timed ---
class CachedChainGroup(Group):
    c5 = providers.Factory(creator=C5, scope=Scope.APP, cache=True)
    c4 = providers.Factory(creator=C4, scope=Scope.APP, cache=True)
    c3 = providers.Factory(creator=C3, scope=Scope.APP, cache=True)
    c2 = providers.Factory(creator=C2, scope=Scope.APP, cache=True)
    c1 = providers.Factory(creator=C1, scope=Scope.APP, cache=True)
    c0 = providers.Factory(creator=C0, scope=Scope.APP, cache=True)


def _cold_build_and_resolve_cached() -> C0:
    container = Container(scope=Scope.APP, groups=[CachedChainGroup])
    container.open()
    return container.resolve_provider(CachedChainGroup.c0)


def test_g8b_cold_first_resolve_cached(benchmark):
    # G8's `cache=True` sibling. G8 is all-transient, so it never reaches
    # `_compile_cached_factory`'s cold-miss builders (`build_cold` / `create_cold`); the only
    # other coverage is incidental inside G15, which batches 50 misses into one timed call and
    # dilutes a single builder ~50x. This times six of them against G8 as the control, so a
    # regression confined to the cached cold path is readable as the G8b/G8 difference.
    result = benchmark(_cold_build_and_resolve_cached)
    assert isinstance(result, C0)
    assert isinstance(result.c1.c2.c3.c4.c5, C5)
