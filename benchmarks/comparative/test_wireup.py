# ruff: noqa: ANN001, ANN201
"""Comparative tier — wireup (2.12.0).

C1/C3 (transient) require an active scope; it is entered once in setup so only
resolution is timed. C2 (singleton, wireup's default) resolves from the root.
C4's async-generator scoped factory forces the async container, whose .get() is
a coroutine, so C4 measures the async scoped lifecycle.
"""

import asyncio
from collections.abc import AsyncIterator

import wireup


@wireup.injectable(lifetime="transient")
class Dep:
    pass


@wireup.injectable(lifetime="transient")
class Service:
    def __init__(self, dep: Dep) -> None:
        self.dep = dep


@wireup.injectable
class SDep:
    pass


@wireup.injectable
class SingletonService:
    def __init__(self, dep: SDep) -> None:
        self.dep = dep


@wireup.injectable(lifetime="transient")
class C5:
    pass


@wireup.injectable(lifetime="transient")
class C4:
    def __init__(self, n: C5) -> None:
        self.n = n


@wireup.injectable(lifetime="transient")
class C3:
    def __init__(self, n: C4) -> None:
        self.n = n


@wireup.injectable(lifetime="transient")
class C2:
    def __init__(self, n: C3) -> None:
        self.n = n


@wireup.injectable(lifetime="transient")
class C1:
    def __init__(self, n: C2) -> None:
        self.n = n


@wireup.injectable(lifetime="transient")
class C0:
    def __init__(self, n: C1) -> None:
        self.n = n


class Connection:
    def __init__(self) -> None:
        self.closed = False


@wireup.injectable(lifetime="scoped")
async def connection_factory() -> AsyncIterator[Connection]:
    conn = Connection()
    try:
        yield conn
    finally:
        await asyncio.sleep(0)
        conn.closed = True


def test_c1_transient(benchmark):
    container = wireup.create_sync_container(injectables=[Dep, Service])
    with container.enter_scope() as scope:
        result = benchmark(scope.get, Service)
    assert isinstance(result, Service)


def test_c2_singleton(benchmark):
    container = wireup.create_sync_container(injectables=[SDep, SingletonService])
    container.get(SingletonService)  # warm
    result = benchmark(container.get, SingletonService)
    assert isinstance(result, SingletonService)


def test_c3_deep_chain(benchmark):
    container = wireup.create_sync_container(injectables=[C0, C1, C2, C3, C4, C5])
    with container.enter_scope() as scope:
        result = benchmark(scope.get, C0)
    assert isinstance(result, C0)


def test_c4_request_lifecycle(benchmark):
    container = wireup.create_async_container(injectables=[connection_factory])
    loop = asyncio.new_event_loop()

    async def _run() -> Connection:
        async with container.enter_scope() as scope:
            return await scope.get(Connection)

    def _one() -> Connection:
        return loop.run_until_complete(_run())

    try:
        result = benchmark(_one)
    finally:
        loop.close()
    assert result.closed is True


# --- C5 cold: create_sync_container (codegen/exec) + first resolve, per call --
# wireup exec-codegens a factory per provider inside create_sync_container, so this is dominated
# by container construction, not resolution (see README caveat).
def test_c5_cold_first_resolve(benchmark):
    def _cold():
        container = wireup.create_sync_container(injectables=[C0, C1, C2, C3, C4, C5])
        with container.enter_scope() as scope:
            return scope.get(C0)

    result = benchmark(_cold)
    assert isinstance(result, C0)


# --- C6 context: per-request runtime value by type via enter_scope(provided) --
class RequestObj:
    def __init__(self) -> None:
        pass


@wireup.injectable(lifetime="scoped")
def _request_placeholder() -> RequestObj:
    # Never called: the value is always supplied via enter_scope; the scoped factory finds the
    # seeded object first. Registration is required so the type is a known by-type dependency.
    raise RuntimeError("RequestObj is only available during a request")


@wireup.injectable
class CtxSettings:
    pass


@wireup.injectable(lifetime="scoped")
class CtxHandler:
    def __init__(self, req: RequestObj, settings: CtxSettings) -> None:
        self.req = req
        self.settings = settings


def test_c6_context(benchmark):
    container = wireup.create_sync_container(injectables=[_request_placeholder, CtxSettings, CtxHandler])

    def _one_request():
        with container.enter_scope({RequestObj: RequestObj()}) as scope:
            return scope.get(CtxHandler)

    result = benchmark(_one_request)
    assert isinstance(result, CtxHandler)
    assert isinstance(result.req, RequestObj)
