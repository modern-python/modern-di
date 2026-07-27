# ruff: noqa: ANN001, ANN201
"""Comparative tier — dishka (1.10.1).

C1-C3 resolve synchronously via make_container.get(). C4's async finalizer forces
the async container: get_sync() raises on an async-generator factory, so the
resolve is awaited and C4 measures the full async request lifecycle.
"""

import asyncio
from collections.abc import AsyncIterable

from dishka import Provider, Scope, from_context, make_async_container, make_container, provide

_BATCH = 100

# Pinned timing shape for C1-C4 and C6; must match every other comparative file (see test_modern_di.py).
_ROUNDS = 200
_ITERATIONS = 1000
_C4_ROUNDS = 100
_C4_ITERATIONS = 3


class Dep:
    pass


class Service:
    def __init__(self, dep: Dep) -> None:
        self.dep = dep


class C5:
    pass


class C4:
    def __init__(self, n: C5) -> None:
        self.n = n


class C3:
    def __init__(self, n: C4) -> None:
        self.n = n


class C2:
    def __init__(self, n: C3) -> None:
        self.n = n


class C1:
    def __init__(self, n: C2) -> None:
        self.n = n


class C0:
    def __init__(self, n: C1) -> None:
        self.n = n


class Connection:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class ConnProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def conn(self) -> AsyncIterable[Connection]:
        c = Connection()
        yield c
        await c.aclose()


def test_c1_transient_dishka(benchmark):
    p = Provider(scope=Scope.APP)
    p.provide(Dep, cache=False)
    p.provide(Service, cache=False)
    container = make_container(p)
    result = benchmark.pedantic(container.get, args=(Service,), rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1)
    assert isinstance(result, Service)


def test_c2_singleton_dishka(benchmark):
    p = Provider(scope=Scope.APP)
    p.provide(Dep)
    p.provide(Service)
    container = make_container(p)
    container.get(Service)
    result = benchmark.pedantic(container.get, args=(Service,), rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1)
    assert isinstance(result, Service)


def test_c3_deep_chain_dishka(benchmark):
    p = Provider(scope=Scope.APP)
    for cls in (C0, C1, C2, C3, C4, C5):
        p.provide(cls, cache=False)
    container = make_container(p)
    result = benchmark.pedantic(container.get, args=(C0,), rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1)
    assert isinstance(result, C0)


def test_c4_request_lifecycle_dishka(benchmark):
    container = make_async_container(ConnProvider())
    loop = asyncio.new_event_loop()

    async def _one() -> Connection:
        async with container() as req:
            return await req.get(Connection)

    async def _batch() -> list[Connection]:
        return [await _one() for _ in range(_BATCH)]

    def _run_batch() -> list[Connection]:
        return loop.run_until_complete(_batch())

    try:
        result = benchmark.pedantic(_run_batch, rounds=_C4_ROUNDS, iterations=_C4_ITERATIONS, warmup_rounds=1)
    finally:
        loop.run_until_complete(container.close())
        loop.close()
    assert len(result) == _BATCH
    assert all(conn.closed for conn in result)


# --- C5 cold: build Provider + make_container + first resolve, per call -------
def test_c5_cold_first_resolve_dishka(benchmark):
    def _cold():
        p = Provider(scope=Scope.APP)
        for cls in (C0, C1, C2, C3, C4, C5):
            p.provide(cls, cache=False)
        container = make_container(p, skip_validation=True)  # align with modern-di: never validates implicitly
        return container.get(C0)

    result = benchmark(_cold)
    assert isinstance(result, C0)


# --- C6 context: per-request runtime value via from_context + APP dep ---------
class RequestObj:
    pass


class Settings:
    pass


class Handler:
    def __init__(self, req: RequestObj, settings: Settings) -> None:
        self.req = req
        self.settings = settings


class _AppProvider(Provider):
    settings = provide(Settings, scope=Scope.APP)


class _ReqProvider(Provider):
    req = from_context(RequestObj, scope=Scope.REQUEST)
    handler = provide(Handler, scope=Scope.REQUEST)


def test_c6_context_dishka(benchmark):
    container = make_container(_AppProvider(), _ReqProvider())

    def _one_request():
        with container(context={RequestObj: RequestObj()}) as req:
            return req.get(Handler)

    try:
        result = benchmark.pedantic(_one_request, rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1)
    finally:
        container.close()
    assert isinstance(result, Handler)
    assert isinstance(result.req, RequestObj)
