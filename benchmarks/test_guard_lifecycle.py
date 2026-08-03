# ruff: noqa: ANN001, ANN201
"""Guard tier — per-request lifecycle scenarios.

G6 measures child-container construction. G7 times a batch of K=100 request
cycles inside one run_until_complete: the full realistic cycle (build REQUEST
child -> sync-init cached resolve -> async finalize via close_async()) repeated
K times per loop entry to isolate DI work from the ~27us event-loop entry cost.
Divide G7's number by 100 for per-request cost. G7c is the control (K=100 empty
awaits on the same shape) so the residual loop overhead is visible (~15% at K=100).
See benchmarks/README.md.
"""

import asyncio
import dataclasses

from benchmarks._pinned import ITER_UNDER_1US, ROUNDS
from modern_di import Container, Group, Scope, providers


_BATCH = 100


@dataclasses.dataclass(slots=True)
class AppService:
    pass


class BuildGroup(Group):
    app_svc = providers.Factory(creator=AppService, scope=Scope.APP)


def test_g6_build_child_container(benchmark):
    app = Container(scope=Scope.APP, groups=[BuildGroup])
    app.open()
    result = benchmark.pedantic(
        app.build_child_container, kwargs={"scope": Scope.REQUEST}, rounds=ROUNDS, iterations=ITER_UNDER_1US
    )
    assert result.scope is Scope.REQUEST


def test_g6b_build_child_container_auto_scope(benchmark):
    # Default path: no explicit scope -> auto-increment via _next_deeper. G6 passes an explicit
    # scope and never exercises it; this guards the memoized auto-increment step against regressing.
    app = Container(scope=Scope.APP, groups=[BuildGroup])
    app.open()
    result = benchmark.pedantic(app.build_child_container, rounds=ROUNDS, iterations=ITER_UNDER_1US)
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


def test_g7_request_lifecycle_batch(benchmark):
    # K request cycles inside ONE run_until_complete: a single loop entry costs ~27us regardless of
    # the body, which swamped the ~2us of real work when each iteration entered the loop separately.
    # The number is a BATCH of _BATCH requests; divide by _BATCH for per-request. Pair it with
    # test_g7c_event_loop_floor_control, which measures the residual entry cost on the same shape.
    app = Container(scope=Scope.APP, groups=[LifecycleGroup])
    app.open()
    loop = asyncio.new_event_loop()

    async def _one_request() -> Connection:
        req = app.build_child_container(scope=Scope.REQUEST)
        req.open()
        conn = req.resolve_provider(LifecycleGroup.conn)
        await req.close_async()
        return conn

    async def _batch() -> list[Connection]:
        return [await _one_request() for _ in range(_BATCH)]

    def _run_batch() -> list[Connection]:
        return loop.run_until_complete(_batch())

    try:
        result = benchmark(_run_batch)
    finally:
        loop.close()
    assert len(result) == _BATCH
    assert all(conn.closed for conn in result)  # every async finalizer ran


def test_g7c_event_loop_floor_control(benchmark):
    # Control, not a subject: the same batch shape with an empty body, so the residual event-loop
    # cost inside every G7 batch number is visible in the same run rather than asserted in prose.
    # Read it as a share of test_g7_request_lifecycle_batch (~15% at _BATCH = 100).
    loop = asyncio.new_event_loop()

    async def _nothing() -> None:
        return None

    async def _batch() -> None:
        for _ in range(_BATCH):
            await _nothing()

    def _run_batch() -> None:
        loop.run_until_complete(_batch())

    try:
        benchmark(_run_batch)
    finally:
        loop.close()


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
    app = Container(scope=Scope.APP, groups=[_TEARDOWN_GROUP])
    app.open()

    def _one_request() -> Container:
        req = app.build_child_container(scope=Scope.REQUEST)
        req.open()  # fresh child per request; part of the measured request cycle, like the close below
        for provider in _TEARDOWN_PROVIDERS:
            req.resolve_provider(provider)
        req.close_sync()  # finalizes all 10 in reverse creation order
        return req

    result = benchmark(_one_request)
    assert result.closed is True
