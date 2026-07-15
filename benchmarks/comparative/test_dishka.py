# ruff: noqa: ANN001, ANN201
"""Comparative tier — dishka (1.10.1).

C1-C3 resolve synchronously via make_container.get(). C4's async finalizer forces
the async container: get_sync() raises on an async-generator factory, so the
resolve is awaited and C4 measures the full async request lifecycle.
"""

import asyncio
from collections.abc import AsyncIterable

from dishka import Provider, Scope, make_async_container, make_container, provide


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


def test_c1_transient(benchmark):
    p = Provider(scope=Scope.APP)
    p.provide(Dep, cache=False)
    p.provide(Service, cache=False)
    container = make_container(p)
    result = benchmark(container.get, Service)
    assert isinstance(result, Service)


def test_c2_singleton(benchmark):
    p = Provider(scope=Scope.APP)
    p.provide(Dep)
    p.provide(Service)
    container = make_container(p)
    container.get(Service)
    result = benchmark(container.get, Service)
    assert isinstance(result, Service)


def test_c3_deep_chain(benchmark):
    p = Provider(scope=Scope.APP)
    for cls in (C0, C1, C2, C3, C4, C5):
        p.provide(cls, cache=False)
    container = make_container(p)
    result = benchmark(container.get, C0)
    assert isinstance(result, C0)


def test_c4_request_lifecycle(benchmark):
    container = make_async_container(ConnProvider())
    loop = asyncio.new_event_loop()

    async def _run() -> Connection:
        async with container() as req:
            return await req.get(Connection)

    def _one() -> Connection:
        return loop.run_until_complete(_run())

    try:
        result = benchmark(_one)
    finally:
        loop.run_until_complete(container.close())
        loop.close()
    assert result.closed is True
