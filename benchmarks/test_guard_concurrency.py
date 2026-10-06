# ruff: noqa: ANN001, ANN201
"""Guard tier — concurrent-resolution throughput (custom N-thread harness).

pytest-benchmark measures single-thread wall time, so these time a *parallel batch* (one job run
by each of N persistent worker threads, released together behind a barrier) as one unit,
parametrized over thread count so the scaling curve is visible **within a single interpreter run**
(no cross-interpreter comparison needed). The workers are started once per benchmark, outside the
timed call, so a batch costs two barrier crossings and no thread start-up. Sub-cases:

- G14 concurrent cached-hit: a fixed total number of reads of a warm cached singleton, split
  across N threads. The cached-hit path is lock-free, so on a free-threaded build (PEP 703) the
  batch time should *drop* as N rises (throughput scales); under the GIL it stays flat.
- G15 concurrent first-resolve: N threads each race to resolve the *same* K cold singletons, so
  they contend on each item's double-checked creation lock (`CacheItem.get_or_create`). Creating
  one singleton is serialized by design, so this is expected *not* to scale even free-threaded: the
  measured cost is the contention itself (the known trade-off vs lock-free-slot rivals).
- G15b concurrent first-resolve in sibling children: the same K cold misses, each thread in its
  own REQUEST child, so no two threads share a cache item.
- G15c control: an empty job on the same pool, the harness floor inside every batch above.

Read the batch-time-vs-thread-count trend, not the absolutes. The GIL vs free-threaded comparison
comes from running the whole file under each build (same version/arch), e.g.:

    uv run --python 3.14t --with pytest-benchmark pytest benchmarks/test_guard_concurrency.py

CI's guard-bench runs one GIL interpreter. Throughput benchmarks are noisier than the single-thread
guards; treat them as guidance. See benchmarks/README.md.
"""

import dataclasses
import threading
import typing

import pytest

from modern_di import Container, Group, Scope, providers


_THREAD_COUNTS = [1, 2, 4]
_TIMEOUT = 30


class _WorkerPool:
    """N persistent threads that each run the current job once per :meth:`run`."""

    def __init__(self, n_threads: int) -> None:
        self._start = threading.Barrier(n_threads + 1, timeout=_TIMEOUT)
        self._done = threading.Barrier(n_threads + 1, timeout=_TIMEOUT)
        self._job: typing.Callable[[int], object] = lambda _: None
        self._stopping = False
        self._errors: list[BaseException] = []
        self.results: list[object] = [None] * n_threads
        self._threads = [threading.Thread(target=self._loop, args=(i,), daemon=True) for i in range(n_threads)]
        for thread in self._threads:
            thread.start()

    def _loop(self, index: int) -> None:
        while True:
            self._start.wait()
            if self._stopping:
                return
            try:
                self.results[index] = self._job(index)
            except BaseException as exc:  # noqa: BLE001
                self._errors.append(exc)
            self._done.wait()

    def run(self, job: typing.Callable[[int], object]) -> None:
        self._job = job
        self._start.wait()
        self._done.wait()
        if self._errors:
            raise self._errors[0]

    def stop(self) -> None:
        self._stopping = True
        self._start.wait()
        for thread in self._threads:
            thread.join(timeout=_TIMEOUT)


@pytest.fixture
def pool(n_threads: int) -> typing.Iterator[_WorkerPool]:
    worker_pool = _WorkerPool(n_threads)
    yield worker_pool
    worker_pool.stop()


# --- G14: concurrent cached-hit (lock-free read path, fixed total work) -----
@dataclasses.dataclass(slots=True)
class CachedSingleton:
    pass


class CachedGroup(Group):
    obj = providers.Factory(creator=CachedSingleton, scope=Scope.APP, cache=True)


_TOTAL_READS = 8000


@pytest.mark.parametrize("n_threads", _THREAD_COUNTS)
def test_g14_concurrent_cached_hit(benchmark, n_threads, pool):
    # Fixed total reads split across N threads: batch time drops with N iff the read path scales.
    container = Container(scope=Scope.APP, groups=[CachedGroup])
    warm = container.resolve_provider(CachedGroup.obj)
    reads_per_thread = _TOTAL_READS // n_threads

    def _job(_: int) -> object:
        result = None
        for _ in range(reads_per_thread):
            result = container.resolve_provider(CachedGroup.obj)
        return result

    benchmark(pool.run, _job)
    assert all(result is warm for result in pool.results)


# --- G15: concurrent first-resolve (creation under the double-checked lock) --
_K_COLD = 50
_COLD_TYPES = [type(f"Cold{i}", (), {}) for i in range(_K_COLD)]
_COLD_GROUP = type(
    "ColdGroup",
    (Group,),
    {f"c{i}": providers.Factory(creator=t, scope=Scope.APP, cache=True) for i, t in enumerate(_COLD_TYPES)},
)
_COLD_PROVIDERS = [getattr(_COLD_GROUP, f"c{i}") for i in range(_K_COLD)]


@pytest.mark.parametrize("n_threads", _THREAD_COUNTS)
def test_g15_concurrent_first_resolve(benchmark, pool):
    # All N threads race to first-resolve the SAME K cold singletons -> contention on each
    # creation lock. Resolvers are compiled once up front; the untimed per-round setup only empties
    # the cache, so every round creates and none compiles.
    container = Container(scope=Scope.APP, groups=[_COLD_GROUP])
    for provider in _COLD_PROVIDERS:
        container.resolve_provider(provider)

    def _setup() -> None:
        container.close_sync()
        container.open()

    def _job(_: int) -> list[object]:
        return [container.resolve_provider(provider) for provider in _COLD_PROVIDERS]

    benchmark.pedantic(pool.run, args=(_job,), setup=_setup, rounds=120, iterations=1)
    first = typing.cast("list[object]", pool.results[0])
    assert [type(obj) for obj in first] == _COLD_TYPES
    assert all(
        all(mine is theirs for mine, theirs in zip(typing.cast("list[object]", result), first, strict=True))
        for result in pool.results
    )


# --- G15b: concurrent first-resolve in sibling children ---------------------
_REQUEST_TYPES = [type(f"ReqCold{i}", (), {}) for i in range(_K_COLD)]
_REQUEST_GROUP = type(
    "RequestColdGroup",
    (Group,),
    {f"r{i}": providers.Factory(creator=t, scope=Scope.REQUEST, cache=True) for i, t in enumerate(_REQUEST_TYPES)},
)
_REQUEST_PROVIDERS = [getattr(_REQUEST_GROUP, f"r{i}") for i in range(_K_COLD)]


@pytest.mark.parametrize("n_threads", _THREAD_COUNTS)
def test_g15b_concurrent_first_resolve_sibling_children(benchmark, n_threads, pool):
    """Each thread builds its own REQUEST child and first-resolves K cached providers in it.

    Every creation is a cold miss in a container no other thread touches. Each cache item has its
    own lock, so these creations never contend; under a lock shared by the tree they would
    serialize. G15 does not cover this: it races on one root's items, whose locks are shared.
    """
    container = Container(scope=Scope.APP, groups=[_REQUEST_GROUP])
    with container.build_child_container(scope=Scope.REQUEST) as probe:
        for provider in _REQUEST_PROVIDERS:
            probe.resolve_provider(provider)

    def _job(_: int) -> list[object]:
        child = container.build_child_container(scope=Scope.REQUEST)
        return [child.resolve_provider(provider) for provider in _REQUEST_PROVIDERS]

    benchmark.pedantic(pool.run, args=(_job,), rounds=120, iterations=1)
    results = [typing.cast("list[object]", result) for result in pool.results]
    assert all([type(obj) for obj in result] == _REQUEST_TYPES for result in results)
    assert len({id(obj) for result in results for obj in result}) == n_threads * _K_COLD


# --- G15c: control, the harness floor ----------------------------------------
@pytest.mark.parametrize("n_threads", _THREAD_COUNTS)
def test_g15c_worker_pool_floor_control(benchmark, n_threads, pool):
    # Control, not a subject: the same batch with an empty job, so the barrier cost inside every
    # G14/G15/G15b number is visible in the same run.
    benchmark.pedantic(pool.run, args=(lambda index: index,), rounds=120, iterations=1)
    assert pool.results == list(range(n_threads))
