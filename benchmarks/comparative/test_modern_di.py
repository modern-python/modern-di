# ruff: noqa: ANN001, ANN201
"""Comparative tier — modern-di reference. Mirror this shape per framework.

Three fairness rules this file must keep:
- Subject classes are plain `__init__` classes, identical in shape to every rival file. A
  `dataclass(slots=True)` subject constructs ~10% cheaper, and construction is inside the timed call.
- C1-C3 exist in BOTH by-reference (`resolve_provider`) and by-type (`resolve`) form. dishka and
  wireup have no by-reference API; that-depends and dependency-injector are by-reference. No single
  variant is fair to both halves of the rival set, so the table compares each against its match.
- A container is open from construction (3.1), so no *timed* body of a published scenario calls
  `open()`: it would time a redundant lock acquire against rivals that need a real scope entry.
  (Unpublished C5 times a cold build and keeps its `open()`, which is part of what it measures.) Per-request work is
  build child -> resolve -> close, and every timed body closes what it opened, because all four
  rivals exit a scope inside theirs.
- Every published scenario (C1-C4, C6) is timed with `benchmark.pedantic` at a pinned
  `rounds x iterations`, identical in all five files. See the note on the constants below.
"""

import asyncio

from modern_di import Container, Group, Scope, providers


_BATCH = 100

# Pinned timing shape for the published scenarios (C1-C4, C6). pytest-benchmark's auto-calibration
# picks `iterations` per benchmark, so one cell can land at iterations=1 while the cell it is
# divided by lands at 25: the first carries the whole per-round timer pair and sits on the
# platform timer's ~42 ns grid, the second amortizes both away. A published ratio must not divide
# a grid-snapped number by an unsnapped one, so every framework pins the same values.
# `warmup_rounds=1` replaces the warm-up that calibration used to provide free.
_ROUNDS = 200
_ITERATIONS = 1000
# C4 is already a batch of _BATCH cycles (>=147 us per call), so a handful of iterations puts the
# timer pair below 0.01% of the cell while keeping enough rounds for a stable median.
_C4_ROUNDS = 100
_C4_ITERATIONS = 3


class Dep:
    pass


class Service:
    def __init__(self, dep: Dep) -> None:
        self.dep = dep


class TransientGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP)
    svc = providers.Factory(creator=Service, scope=Scope.APP)


class SingletonGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP, cache=True)
    svc = providers.Factory(creator=Service, scope=Scope.APP, cache=True)


class C5:
    pass


class C4:
    def __init__(self, c5: C5) -> None:
        self.c5 = c5


class C3:
    def __init__(self, c4: C4) -> None:
        self.c4 = c4


class C2:
    def __init__(self, c3: C3) -> None:
        self.c3 = c3


class C1:
    def __init__(self, c2: C2) -> None:
        self.c2 = c2


class C0:
    def __init__(self, c1: C1) -> None:
        self.c1 = c1


class ChainGroup(Group):
    c5 = providers.Factory(creator=C5, scope=Scope.APP)
    c4 = providers.Factory(creator=C4, scope=Scope.APP)
    c3 = providers.Factory(creator=C3, scope=Scope.APP)
    c2 = providers.Factory(creator=C2, scope=Scope.APP)
    c1 = providers.Factory(creator=C1, scope=Scope.APP)
    c0 = providers.Factory(creator=C0, scope=Scope.APP)


class Connection:
    def __init__(self) -> None:
        self.closed = False


async def _close_connection(conn: Connection) -> None:
    conn.closed = True


class LifecycleGroup(Group):
    conn = providers.Factory(
        creator=Connection,
        scope=Scope.REQUEST,
        cache=providers.CacheSettings(finalizer=_close_connection),
    )


# --- C1: transient, by reference and by type --------------------------------
def test_c1_transient_by_ref_modern_di(benchmark):
    c = Container(scope=Scope.APP, groups=[TransientGroup])
    c.open()
    result = benchmark.pedantic(
        c.resolve_provider, args=(TransientGroup.svc,), rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1
    )
    assert isinstance(result, Service)


def test_c1_transient_by_type_modern_di(benchmark):
    c = Container(scope=Scope.APP, groups=[TransientGroup])
    c.open()
    result = benchmark.pedantic(c.resolve, args=(Service,), rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1)
    assert isinstance(result, Service)


# --- C2: warm singleton, by reference and by type ---------------------------
def test_c2_singleton_by_ref_modern_di(benchmark):
    c = Container(scope=Scope.APP, groups=[SingletonGroup])
    c.open()
    c.resolve_provider(SingletonGroup.svc)  # warm
    result = benchmark.pedantic(
        c.resolve_provider, args=(SingletonGroup.svc,), rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1
    )
    assert isinstance(result, Service)


def test_c2_singleton_by_type_modern_di(benchmark):
    c = Container(scope=Scope.APP, groups=[SingletonGroup])
    c.open()
    c.resolve(Service)  # warm
    result = benchmark.pedantic(c.resolve, args=(Service,), rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1)
    assert isinstance(result, Service)


# --- C3: depth-6 chain, by reference and by type ----------------------------
def test_c3_deep_chain_by_ref_modern_di(benchmark):
    c = Container(scope=Scope.APP, groups=[ChainGroup])
    c.open()
    result = benchmark.pedantic(
        c.resolve_provider, args=(ChainGroup.c0,), rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1
    )
    assert isinstance(result, C0)


def test_c3_deep_chain_by_type_modern_di(benchmark):
    c = Container(scope=Scope.APP, groups=[ChainGroup])
    c.open()
    result = benchmark.pedantic(c.resolve, args=(C0,), rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1)
    assert isinstance(result, C0)


# --- C4: request lifecycle, batched (see benchmarks/README.md) --------------
def test_c4_request_lifecycle_modern_di(benchmark):
    app = Container(scope=Scope.APP, groups=[LifecycleGroup])
    app.open()
    loop = asyncio.new_event_loop()

    async def _one_request() -> Connection:
        req = app.build_child_container(scope=Scope.REQUEST)
        conn = req.resolve_provider(LifecycleGroup.conn)
        await req.close_async()
        return conn

    async def _batch() -> list[Connection]:
        return [await _one_request() for _ in range(_BATCH)]

    def _run_batch() -> list[Connection]:
        return loop.run_until_complete(_batch())

    try:
        result = benchmark.pedantic(_run_batch, rounds=_C4_ROUNDS, iterations=_C4_ITERATIONS, warmup_rounds=1)
    finally:
        loop.close()
    assert len(result) == _BATCH
    assert all(conn.closed for conn in result)


# --- C5 cold: fresh container build + first-resolve compile of the chain -----
def test_c5_cold_first_resolve_modern_di(benchmark):
    def _cold():
        c = Container(scope=Scope.APP, groups=[ChainGroup])
        c.open()
        return c.resolve_provider(ChainGroup.c0)

    result = benchmark(_cold)
    assert isinstance(result, C0)


# --- C6 context: per-request runtime value by type + a shared app dep --------
class RequestObj:
    pass


class AppDep:
    pass


class Handler:
    def __init__(self, req: RequestObj, dep: AppDep) -> None:
        self.req = req
        self.dep = dep


class ContextGroup(Group):
    app_dep = providers.Factory(creator=AppDep, scope=Scope.APP, cache=True)
    req_ctx = providers.ContextProvider(RequestObj, scope=Scope.REQUEST)
    handler = providers.Factory(creator=Handler, scope=Scope.REQUEST)


def test_c6_context_modern_di(benchmark):
    app = Container(scope=Scope.APP, groups=[ContextGroup])
    app.open()

    def _one_request():
        req = app.build_child_container(scope=Scope.REQUEST, context={RequestObj: RequestObj()})
        handler = req.resolve_provider(ContextGroup.handler)
        req.close_sync()
        return handler

    result = benchmark.pedantic(_one_request, rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1)
    assert isinstance(result, Handler)
    assert isinstance(result.req, RequestObj)
    assert isinstance(result.dep, AppDep)
