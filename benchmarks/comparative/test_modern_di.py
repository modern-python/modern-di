# ruff: noqa: ANN001, ANN201
"""Comparative tier — modern-di reference. Mirror this shape per framework."""

import asyncio
import dataclasses

from modern_di import Container, Group, Scope, providers


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


@dataclasses.dataclass(slots=True)
class Connection:
    closed: bool = False


async def _close_connection(conn: Connection) -> None:
    conn.closed = True


class LifecycleGroup(Group):
    conn = providers.Factory(
        creator=Connection,
        scope=Scope.REQUEST,
        cache=providers.CacheSettings(finalizer=_close_connection),
    )


def test_c1_transient(benchmark):
    c = Container(scope=Scope.APP, groups=[TransientGroup], validate=False)
    result = benchmark(c.resolve_provider, TransientGroup.svc)
    assert isinstance(result, Service)


def test_c2_singleton(benchmark):
    c = Container(scope=Scope.APP, groups=[SingletonGroup], validate=False)
    c.resolve_provider(SingletonGroup.svc)
    result = benchmark(c.resolve_provider, SingletonGroup.svc)
    assert isinstance(result, Service)


def test_c3_deep_chain(benchmark):
    c = Container(scope=Scope.APP, groups=[ChainGroup], validate=False)
    result = benchmark(c.resolve_provider, ChainGroup.c0)
    assert isinstance(result, C0)


def test_c4_request_lifecycle(benchmark):
    app = Container(scope=Scope.APP, groups=[LifecycleGroup], validate=False)
    loop = asyncio.new_event_loop()

    async def _run() -> Connection:
        req = app.build_child_container(scope=Scope.REQUEST)
        conn = req.resolve_provider(LifecycleGroup.conn)
        await req.close_async()
        return conn

    def _one_request() -> Connection:
        return loop.run_until_complete(_run())

    try:
        result = benchmark(_one_request)
    finally:
        loop.close()
    assert isinstance(result, Connection)
    assert result.closed is True


# --- C5 cold: fresh container build + first-resolve compile of the chain -----
def test_c5_cold_first_resolve(benchmark):
    def _cold():
        c = Container(scope=Scope.APP, groups=[ChainGroup], validate=False)
        return c.resolve_provider(ChainGroup.c0)

    result = benchmark(_cold)
    assert isinstance(result, C0)


# --- C6 context: per-request runtime value by type + a shared app dep --------
class RequestObj:
    pass


@dataclasses.dataclass(slots=True)
class AppDep:
    pass


@dataclasses.dataclass(slots=True)
class Handler:
    req: RequestObj
    dep: AppDep


class ContextGroup(Group):
    app_dep = providers.Factory(creator=AppDep, scope=Scope.APP, cache=True)
    req_ctx = providers.ContextProvider(RequestObj, scope=Scope.REQUEST)
    handler = providers.Factory(creator=Handler, scope=Scope.REQUEST)


def test_c6_context(benchmark):
    app = Container(scope=Scope.APP, groups=[ContextGroup], validate=False)

    def _one_request():
        req = app.build_child_container(scope=Scope.REQUEST, context={RequestObj: RequestObj()})
        return req.resolve_provider(ContextGroup.handler)

    result = benchmark(_one_request)
    assert isinstance(result, Handler)
    assert isinstance(result.req, RequestObj)
    assert isinstance(result.dep, AppDep)
