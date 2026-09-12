# ruff: noqa: ANN001, ANN201
"""Guard tier — concurrent-resolution throughput (custom N-thread harness).

pytest-benchmark measures single-thread wall time, so these time a *parallel batch* (N worker
threads released together behind a barrier) as one unit, parametrized over thread count so the
scaling curve is visible **within a single interpreter run** (no cross-interpreter comparison
needed). Two sub-cases:

- G14 concurrent cached-hit: a fixed total number of reads of a warm cached singleton, split
  across N threads. The cached-hit path is lock-free, so on a free-threaded build (PEP 703) the
  batch time should *drop* as N rises (throughput scales); under the GIL it stays flat.
- G15 concurrent first-resolve: N threads each race to resolve the *same* K cold singletons, so
  they contend on the double-checked creation lock (`CacheItem.get_or_create`). Singleton
  creation is serialized by design, so this is expected *not* to scale even free-threaded — the
  measured cost is the contention itself (the known trade-off vs lock-free-slot rivals).

Read the batch-time-vs-thread-count trend, not the absolutes. The GIL vs free-threaded comparison
comes from running the whole file under each build (same version/arch), e.g.:

    uv run --python 3.14t --with pytest-benchmark pytest benchmarks/test_guard_concurrency.py

CI's guard-bench runs one GIL interpreter. Throughput benchmarks are noisier than the single-thread
guards; treat them as guidance. See benchmarks/README.md.
"""

import dataclasses
import threading

import pytest

from modern_di import Container, Group, Scope, providers


_THREAD_COUNTS = [1, 2, 4]


def _run_parallel(worker, n_threads: int) -> None:
    # Release all threads together (barrier) so the work overlaps maximally.
    barrier = threading.Barrier(n_threads)

    def _target() -> None:
        barrier.wait()
        worker()

    threads = [threading.Thread(target=_target) for _ in range(n_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


# --- G14: concurrent cached-hit (lock-free read path, fixed total work) -----
@dataclasses.dataclass(slots=True)
class CachedSingleton:
    pass


class CachedGroup(Group):
    obj = providers.Factory(creator=CachedSingleton, scope=Scope.APP, cache=True)


_TOTAL_READS = 8000


@pytest.mark.parametrize("n_threads", _THREAD_COUNTS)
def test_g14_concurrent_cached_hit(benchmark, n_threads):
    # Fixed total reads split across N threads: batch time drops with N iff the read path scales.
    container = Container(scope=Scope.APP, groups=[CachedGroup])
    container.open()
    warm = container.resolve_provider(CachedGroup.obj)
    reads_per_thread = _TOTAL_READS // n_threads

    def _worker() -> None:
        for _ in range(reads_per_thread):
            container.resolve_provider(CachedGroup.obj)

    benchmark(_run_parallel, _worker, n_threads)
    assert container.resolve_provider(CachedGroup.obj) is warm  # same cached instance


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
def test_g15_concurrent_first_resolve(benchmark, n_threads):
    # All N threads race to first-resolve the SAME K cold singletons -> contention on each
    # creation lock. Fresh container per round (untimed setup) so every round actually creates.
    check = Container(scope=Scope.APP, groups=[_COLD_GROUP])
    check.open()
    assert all(check.resolve_provider(p) is not None for p in _COLD_PROVIDERS)

    def _setup() -> "tuple[tuple[Container], dict[str, object]]":
        container = Container(scope=Scope.APP, groups=[_COLD_GROUP])
        container.open()
        return (container,), {}

    def _batch(container) -> None:
        def _worker() -> None:
            for provider in _COLD_PROVIDERS:
                container.resolve_provider(provider)

        _run_parallel(_worker, n_threads)

    benchmark.pedantic(_batch, setup=_setup, rounds=120, iterations=1)


# --- G15b: concurrent first-resolve in sibling children ---------------------
_REQUEST_TYPES = [type(f"ReqCold{i}", (), {}) for i in range(_K_COLD)]
_REQUEST_GROUP = type(
    "RequestColdGroup",
    (Group,),
    {f"r{i}": providers.Factory(creator=t, scope=Scope.REQUEST, cache=True) for i, t in enumerate(_REQUEST_TYPES)},
)
_REQUEST_PROVIDERS = [getattr(_REQUEST_GROUP, f"r{i}") for i in range(_K_COLD)]


@pytest.mark.parametrize("n_threads", _THREAD_COUNTS)
def test_g15b_concurrent_first_resolve_sibling_children(benchmark, n_threads):
    # Each thread builds its OWN REQUEST child and first-resolves K cached providers in it, so
    # every creation is a cold miss in a container no other thread touches. With a lock per
    # container these creations never contend; with one lock per tree they serialize. This is the
    # scenario G15 does not cover -- G15 races on one root, whose lock is shared either way.
    check = Container(scope=Scope.APP, groups=[_REQUEST_GROUP])
    check.open()
    probe = check.build_child_container(scope=Scope.REQUEST)
    assert all(probe.resolve_provider(p) is not None for p in _REQUEST_PROVIDERS)

    def _setup() -> "tuple[tuple[Container], dict[str, object]]":
        container = Container(scope=Scope.APP, groups=[_REQUEST_GROUP])
        container.open()
        return (container,), {}

    def _batch(container) -> None:
        def _worker() -> None:
            child = container.build_child_container(scope=Scope.REQUEST)
            for provider in _REQUEST_PROVIDERS:
                child.resolve_provider(provider)

        _run_parallel(_worker, n_threads)

    benchmark.pedantic(_batch, setup=_setup, rounds=120, iterations=1)
