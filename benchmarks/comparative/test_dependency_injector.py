# ruff: noqa: ANN001, ANN201
"""Comparative tier — dependency-injector (4.49.1).

C1-C3 resolve synchronously by calling the provider. C4's Resource uses an
async-generator initializer (sync create before yield, async close after), so
init/resolve/shutdown are awaited and C4 measures the async resource lifecycle.
"""

import asyncio

from dependency_injector import containers, providers

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

    async def close(self) -> None:
        self.closed = True


async def _init_connection():
    conn = Connection()
    yield conn
    await conn.close()


class TransientContainer(containers.DeclarativeContainer):
    dep = providers.Factory(Dep)
    service = providers.Factory(Service, dep=dep)


class SingletonContainer(containers.DeclarativeContainer):
    dep = providers.Singleton(Dep)
    service = providers.Singleton(Service, dep=dep)


class ChainContainer(containers.DeclarativeContainer):
    c5 = providers.Factory(C5)
    c4 = providers.Factory(C4, c5=c5)
    c3 = providers.Factory(C3, c4=c4)
    c2 = providers.Factory(C2, c3=c3)
    c1 = providers.Factory(C1, c2=c2)
    c0 = providers.Factory(C0, c1=c1)


class LifecycleContainer(containers.DeclarativeContainer):
    connection = providers.Resource(_init_connection)


def test_c1_transient_dependency_injector(benchmark):
    container = TransientContainer()
    result = benchmark.pedantic(container.service, rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1)
    assert isinstance(result, Service)


def test_c2_singleton_dependency_injector(benchmark):
    container = SingletonContainer()
    container.service()  # warm the singleton
    result = benchmark.pedantic(container.service, rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1)
    assert isinstance(result, Service)


def test_c3_deep_chain_dependency_injector(benchmark):
    container = ChainContainer()
    result = benchmark.pedantic(container.c0, rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1)
    assert isinstance(result, C0)


def test_c4_request_lifecycle_dependency_injector(benchmark):
    # The container is built ONCE in setup, like every other framework here. Building it inside the
    # timed call (as this benchmark used to) deep-copies the provider graph per request -- ~29% of
    # the old number -- a cost a real dependency-injector app pays once at startup.
    container = LifecycleContainer()
    loop = asyncio.new_event_loop()

    async def _one() -> Connection:
        await container.init_resources()
        conn = await container.connection()
        await container.shutdown_resources()
        return conn

    async def _batch() -> list[Connection]:
        return [await _one() for _ in range(_BATCH)]

    def _run_batch() -> list[Connection]:
        return loop.run_until_complete(_batch())

    try:
        result = benchmark.pedantic(_run_batch, rounds=_C4_ROUNDS, iterations=_C4_ITERATIONS, warmup_rounds=1)
    finally:
        loop.close()
    assert len(result) == _BATCH
    assert all(conn.closed for conn in result)


# --- C5 cold: instantiate a fresh container + first resolve, per call ---------
# The DeclarativeContainer subclass wires at class definition (import). Per call this instantiates
# a fresh container (deep-copies the provider graph -- the dominant cost) and resolves; the number
# is ~98% instance clone, not resolution (see README caveat).
def test_c5_cold_first_resolve_dependency_injector(benchmark):
    def _cold():
        container = ChainContainer()
        return container.c0()

    result = benchmark(_cold)
    assert isinstance(result, C0)


# --- C6 context: per-request runtime value via Dependency + override ----------
# dependency-injector wires by provider REFERENCE, not by type: the runtime value is a
# providers.Dependency node supplied per request via .override() (see README caveat).
class RequestObj:
    pass


class AppDep:
    pass


class Handler:
    def __init__(self, app_dep: AppDep, request: RequestObj) -> None:
        self.app_dep = app_dep
        self.request = request


class ContextContainer(containers.DeclarativeContainer):
    app_dep = providers.Singleton(AppDep)
    request = providers.Dependency(instance_of=RequestObj)
    handler = providers.Factory(Handler, app_dep=app_dep, request=request)


def test_c6_context_dependency_injector(benchmark):
    container = ContextContainer()

    def _one_request():
        with container.request.override(RequestObj()):
            return container.handler()

    result = benchmark.pedantic(_one_request, rounds=_ROUNDS, iterations=_ITERATIONS, warmup_rounds=1)
    assert isinstance(result, Handler)
    assert isinstance(result.request, RequestObj)
