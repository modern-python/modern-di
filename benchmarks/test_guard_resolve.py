# ruff: noqa: ANN001, ANN201
"""Guard tier — modern-di resolve hot-path scenarios (zero external deps).

Each benchmark builds/warms its container in setup (outside the timed call) and
measures only resolve. Every function asserts the resolved graph is correct so a
broken setup cannot post a fake-fast number. See benchmarks/README.md.
"""

import dataclasses

from modern_di import Container, Group, Scope, providers


# --- G1 / G2 subject graph: one dependency ---------------------------------
@dataclasses.dataclass(slots=True)
class Dep:
    pass


@dataclasses.dataclass(slots=True)
class Service:
    dep: Dep


class TransientGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP)
    svc = providers.Factory(creator=Service, scope=Scope.APP)


class SingletonGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP, cache=True)
    svc = providers.Factory(creator=Service, scope=Scope.APP, cache=True)


def test_g1_transient_resolve(benchmark):
    container = Container(scope=Scope.APP, groups=[TransientGroup], validate=False)
    result = benchmark(container.resolve_provider, TransientGroup.svc)
    assert isinstance(result, Service)
    assert isinstance(result.dep, Dep)


def test_g2_cached_resolve(benchmark):
    container = Container(scope=Scope.APP, groups=[SingletonGroup], validate=False)
    container.resolve_provider(SingletonGroup.svc)  # warm the cache
    result = benchmark(container.resolve_provider, SingletonGroup.svc)
    assert isinstance(result, Service)


# --- G3 subject graph: depth-6 chain ---------------------------------------
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


def test_g3_deep_chain(benchmark):
    container = Container(scope=Scope.APP, groups=[ChainGroup], validate=False)
    result = benchmark(container.resolve_provider, ChainGroup.c0)
    assert isinstance(result, C0)
    assert isinstance(result.c1.c2.c3.c4.c5, C5)


# --- G4 subject graph: one object, 10 sibling deps -------------------------
@dataclasses.dataclass(slots=True)
class L0:
    pass


@dataclasses.dataclass(slots=True)
class L1:
    pass


@dataclasses.dataclass(slots=True)
class L2:
    pass


@dataclasses.dataclass(slots=True)
class L3:
    pass


@dataclasses.dataclass(slots=True)
class L4:
    pass


@dataclasses.dataclass(slots=True)
class L5:
    pass


@dataclasses.dataclass(slots=True)
class L6:
    pass


@dataclasses.dataclass(slots=True)
class L7:
    pass


@dataclasses.dataclass(slots=True)
class L8:
    pass


@dataclasses.dataclass(slots=True)
class L9:
    pass


@dataclasses.dataclass(slots=True)
class Wide:
    l0: L0
    l1: L1
    l2: L2
    l3: L3
    l4: L4
    l5: L5
    l6: L6
    l7: L7
    l8: L8
    l9: L9


class WideGroup(Group):
    l0 = providers.Factory(creator=L0, scope=Scope.APP)
    l1 = providers.Factory(creator=L1, scope=Scope.APP)
    l2 = providers.Factory(creator=L2, scope=Scope.APP)
    l3 = providers.Factory(creator=L3, scope=Scope.APP)
    l4 = providers.Factory(creator=L4, scope=Scope.APP)
    l5 = providers.Factory(creator=L5, scope=Scope.APP)
    l6 = providers.Factory(creator=L6, scope=Scope.APP)
    l7 = providers.Factory(creator=L7, scope=Scope.APP)
    l8 = providers.Factory(creator=L8, scope=Scope.APP)
    l9 = providers.Factory(creator=L9, scope=Scope.APP)
    wide = providers.Factory(creator=Wide, scope=Scope.APP)


def test_g4_wide_resolve(benchmark):
    container = Container(scope=Scope.APP, groups=[WideGroup], validate=False)
    result = benchmark(container.resolve_provider, WideGroup.wide)
    assert isinstance(result, Wide)
    assert isinstance(result.l9, L9)


# --- G5 subject graph: cross-scope REQUEST -> APP dependency ---------------
@dataclasses.dataclass(slots=True)
class AppService:
    pass


@dataclasses.dataclass(slots=True)
class RequestService:
    app: AppService


class CrossScopeGroup(Group):
    app_svc = providers.Factory(creator=AppService, scope=Scope.APP)
    req_svc = providers.Factory(creator=RequestService, scope=Scope.REQUEST)


def test_g5_cross_scope(benchmark):
    app = Container(scope=Scope.APP, groups=[CrossScopeGroup], validate=False)
    req = app.build_child_container(scope=Scope.REQUEST)
    result = benchmark(req.resolve_provider, CrossScopeGroup.req_svc)
    assert isinstance(result, RequestService)
    assert isinstance(result.app, AppService)


# --- G9 subject graph: context value injected by type + an APP dep ----------
class RequestObj:  # a fresh per-request runtime value (e.g. a framework Request)
    pass


@dataclasses.dataclass(slots=True)
class AppDep:
    pass


@dataclasses.dataclass(slots=True)
class Handler:
    req: RequestObj
    dep: AppDep


class ContextGroup(Group):
    app_dep = providers.Factory(creator=AppDep, scope=Scope.APP)
    req_ctx = providers.ContextProvider(RequestObj, scope=Scope.REQUEST)
    # transient -> folds the runtime context value on every resolve (the non-pure kwargs path)
    handler = providers.Factory(creator=Handler, scope=Scope.REQUEST)


def test_g9_context_resolve(benchmark):
    # Isolates the context-folding (non-pure kwargs) path C1-C5 never touch: a factory mixing a
    # runtime context value with a provider dep. Container + child built in setup; only resolve timed.
    app = Container(scope=Scope.APP, groups=[ContextGroup], validate=False)
    req = app.build_child_container(scope=Scope.REQUEST, context={RequestObj: RequestObj()})
    result = benchmark(req.resolve_provider, ContextGroup.handler)
    assert isinstance(result, Handler)
    assert isinstance(result.req, RequestObj)
    assert isinstance(result.dep, AppDep)


# --- G12 subject graph: depth-6 chain + one unrelated overridable provider ---
class Sentinel:
    pass


class OverrideChainGroup(Group):
    c5 = providers.Factory(creator=C5, scope=Scope.APP)
    c4 = providers.Factory(creator=C4, scope=Scope.APP)
    c3 = providers.Factory(creator=C3, scope=Scope.APP)
    c2 = providers.Factory(creator=C2, scope=Scope.APP)
    c1 = providers.Factory(creator=C1, scope=Scope.APP)
    c0 = providers.Factory(creator=C0, scope=Scope.APP)
    sentinel = providers.Factory(creator=Sentinel, scope=Scope.APP)


def test_g12_override_active_resolve(benchmark):
    # Override front-guard tax: an UNRELATED override flips has_overrides True, so every node in the
    # depth-6 chain pays a fetch_override lookup per resolve (the path a test suite with mocks hits).
    container = Container(scope=Scope.APP, groups=[OverrideChainGroup], validate=False)
    container.override(OverrideChainGroup.sentinel, Sentinel())
    container.resolve_provider(OverrideChainGroup.c0)  # warm
    result = benchmark(container.resolve_provider, OverrideChainGroup.c0)
    assert isinstance(result, C0)
