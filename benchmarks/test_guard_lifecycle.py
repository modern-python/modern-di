# ruff: noqa: ANN001, ANN201
"""Guard tier — per-request lifecycle scenarios.

G6 measures child-container construction. G7 measures the full realistic
request cycle: build REQUEST child -> sync-init cached resolve -> async finalize
via close_async(). G7 is wall-clock only (instruction-count tools cannot measure
the awaited teardown); a single reused event loop keeps loop overhead out of the
per-iteration signal as much as possible. See benchmarks/README.md.
"""

import asyncio
import dataclasses

from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(slots=True)
class AppService:
    pass


class BuildGroup(Group):
    app_svc = providers.Factory(creator=AppService, scope=Scope.APP)


def test_g6_build_child_container(benchmark):
    app = Container(scope=Scope.APP, groups=[BuildGroup], validate=False)
    result = benchmark(app.build_child_container, scope=Scope.REQUEST)
    assert result.scope is Scope.REQUEST


def test_g6b_build_child_container_auto_scope(benchmark):
    # Default path: no explicit scope -> auto-increment via _next_deeper. G6 passes an explicit
    # scope and never exercises it; this guards the memoized auto-increment step against regressing.
    app = Container(scope=Scope.APP, groups=[BuildGroup], validate=False)
    result = benchmark(app.build_child_container)
    assert result.scope is Scope.SESSION


# --- G7: cached REQUEST connection, sync create, async finalizer -----------
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


def test_g7_request_lifecycle(benchmark):
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
    assert result.closed is True  # async finalizer ran


# --- G13: teardown at scale -- 10 cached REQUEST resources, sync finalizers ---
# G7 finalizes one resource; a real request closes several. G13 measures the per-request cycle
# with 10 cached REQUEST providers (each a sync finalizer) so the LIFO close loop is exercised.
def _noop_finalizer(_obj: object) -> None:
    pass


_RES_TYPES = [type(f"Res{i}", (), {}) for i in range(10)]
_TEARDOWN_GROUP = type(
    "TeardownGroup",
    (Group,),
    {
        f"res{i}": providers.Factory(
            creator=t, scope=Scope.REQUEST, cache=providers.CacheSettings(finalizer=_noop_finalizer)
        )
        for i, t in enumerate(_RES_TYPES)
    },
)
_TEARDOWN_PROVIDERS = [getattr(_TEARDOWN_GROUP, f"res{i}") for i in range(len(_RES_TYPES))]


def test_g13_teardown_at_scale(benchmark):
    app = Container(scope=Scope.APP, groups=[_TEARDOWN_GROUP], validate=False)

    def _one_request() -> Container:
        req = app.build_child_container(scope=Scope.REQUEST)
        for provider in _TEARDOWN_PROVIDERS:
            req.resolve_provider(provider)
        req.close_sync()  # finalizes all 10 in reverse creation order
        return req

    result = benchmark(_one_request)
    assert result.closed is True
