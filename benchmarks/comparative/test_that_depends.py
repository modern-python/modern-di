# ruff: noqa: ANN001, ANN201
"""Comparative tier — that-depends (4.0.2).

C1-C3 resolve synchronously via provider.resolve_sync(). C4's async-generator
ContextResource cannot resolve_sync (raises), so C4 awaits resolve() inside a
request context and measures the full async lifecycle.
"""

import asyncio
import typing

from that_depends import BaseContainer, ContextScopes, container_context, providers


class Dep:
    pass


class Service:
    def __init__(self, dep: Dep) -> None:
        self.dep = dep


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


class Connection:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


async def _connection() -> typing.AsyncIterator[Connection]:
    conn = Connection()
    try:
        yield conn
    finally:
        await conn.aclose()


class TransientContainer(BaseContainer):
    dep = providers.Factory(Dep)
    service = providers.Factory(Service, dep=dep.cast)


class SingletonContainer(BaseContainer):
    dep = providers.Singleton(Dep)
    service = providers.Singleton(Service, dep=dep.cast)


class ChainContainer(BaseContainer):
    c5 = providers.Factory(C5)
    c4 = providers.Factory(C4, c5=c5.cast)
    c3 = providers.Factory(C3, c4=c4.cast)
    c2 = providers.Factory(C2, c3=c3.cast)
    c1 = providers.Factory(C1, c2=c2.cast)
    c0 = providers.Factory(C0, c1=c1.cast)


class LifecycleContainer(BaseContainer):
    default_scope = ContextScopes.REQUEST
    connection = providers.ContextResource(_connection)


def test_c1_transient(benchmark):
    result = benchmark(TransientContainer.service.resolve_sync)
    assert isinstance(result, Service)


def test_c2_singleton(benchmark):
    SingletonContainer.service.resolve_sync()  # warm the cache
    result = benchmark(SingletonContainer.service.resolve_sync)
    assert isinstance(result, Service)


def test_c3_deep_chain(benchmark):
    result = benchmark(ChainContainer.c0.resolve_sync)
    assert isinstance(result, C0)


def test_c4_request_lifecycle(benchmark):
    loop = asyncio.new_event_loop()

    async def _run() -> Connection:
        async with container_context(LifecycleContainer, scope=ContextScopes.REQUEST):
            return await LifecycleContainer.connection.resolve()

    def _one() -> Connection:
        return loop.run_until_complete(_run())

    try:
        result = benchmark(_one)
    finally:
        loop.close()
    assert result.closed is True
