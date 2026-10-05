import asyncio
import dataclasses
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import AsyncFinalizerInSyncCloseError, ContainerClosedError, FinalizerError, ModernDIError
from modern_di.types import UNSET


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class DependentCreator:
    dep1: SimpleCreator


async def async_finalizer(_: DependentCreator) -> None:
    pass


class MyGroup(Group):
    app_cached = providers.Factory(
        creator=SimpleCreator,
        kwargs={"dep1": "original"},
        cache=True,
    )
    request_cached = providers.Factory(
        scope=Scope.REQUEST, creator=DependentCreator, cache=providers.CacheSettings(finalizer=async_finalizer)
    )


async def test_app_cached_factory() -> None:
    sync_calls: list[SimpleCreator] = []

    class LocalGroup(Group):
        cached = providers.Factory(
            creator=SimpleCreator,
            kwargs={"dep1": "original"},
            cache=providers.CacheSettings(clear_cache=False, finalizer=sync_calls.append),
        )

    app_container = Container(groups=[LocalGroup])
    instance1 = app_container.resolve_provider(LocalGroup.cached)
    instance2 = app_container.resolve_provider(LocalGroup.cached)
    assert instance1 is instance2

    app_container.close_sync()
    assert sync_calls == [instance1]  # finalizer ran once on close

    # clear_cache=False: the instance survives the close and is returned again once the container
    # is reopened, without re-running the creator or finalizer.
    with pytest.raises(ContainerClosedError):
        app_container.resolve_provider(LocalGroup.cached)
    app_container.open()
    assert app_container.resolve_provider(LocalGroup.cached) is instance1
    assert sync_calls == [instance1]  # finalizer did not re-fire

    await app_container.close_async()
    assert sync_calls == [instance1]


def test_close_does_not_re_finalize_with_clear_cache_false() -> None:
    calls: list[str] = []

    class G(Group):
        f = providers.Factory(
            creator=lambda: "r",
            bound_type=str,
            cache=providers.CacheSettings(clear_cache=False, finalizer=calls.append),
        )

    container = Container(groups=[G])
    container.resolve(str)
    container.close_sync()
    container.close_sync()
    container.close_sync()
    assert calls == ["r"]


async def test_close_async_runs_sync_finalizer() -> None:
    calls: list[str] = []

    class G(Group):
        f = providers.Factory(
            creator=lambda: "r",
            bound_type=str,
            cache=providers.CacheSettings(finalizer=calls.append),
        )

    container = Container(groups=[G])
    container.resolve(str)
    await container.close_async()
    assert calls == ["r"]


async def test_request_cached_factory() -> None:
    app_container = Container(groups=[MyGroup])
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance1 = request_container.resolve_provider(MyGroup.request_cached)
    instance2 = request_container.resolve(DependentCreator)
    assert isinstance(instance1.dep1, SimpleCreator)
    assert instance1 is instance2

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance3 = request_container.resolve_provider(MyGroup.request_cached)
    instance4 = request_container.resolve(DependentCreator)
    assert instance3 is instance4
    assert instance1 is not instance3

    cache_item = request_container._cache_registry.fetch_cache_item(MyGroup.request_cached)

    with pytest.raises(FinalizerError) as exc_info:
        request_container.close_sync()
    assert exc_info.value.is_async is False
    assert len(exc_info.value.exceptions) == 1
    assert isinstance(exc_info.value.exceptions[0], AsyncFinalizerInSyncCloseError)

    assert cache_item.cache is not UNSET  # preserved — user can still recover via close_async
    await request_container.close_async()

    assert cache_item.cache is UNSET


def test_app_cached_factory_resolves_once_across_request_children() -> None:
    app_container = Container(groups=[MyGroup])
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance1 = request_container.resolve_provider(MyGroup.app_cached)

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance2 = request_container.resolve_provider(MyGroup.app_cached)

    assert instance1 is instance2


def test_sync_finalizer_exception_does_not_abort_remaining_cleanup() -> None:
    cleaned_up: list[str] = []

    def failing_finalizer(_: SimpleCreator) -> None:
        msg = "finalizer failed"
        raise RuntimeError(msg)

    def good_finalizer(_: SimpleCreator) -> None:
        cleaned_up.append("done")

    class BrokenGroup(Group):
        first = providers.Factory(
            creator=SimpleCreator,
            kwargs={"dep1": "first"},
            cache=providers.CacheSettings(finalizer=failing_finalizer),
        )
        second = providers.Factory(
            creator=SimpleCreator,
            bound_type=None,
            kwargs={"dep1": "second"},
            cache=providers.CacheSettings(finalizer=good_finalizer),
        )

    app_container = Container(groups=[BrokenGroup])
    app_container.resolve_provider(BrokenGroup.first)
    app_container.resolve_provider(BrokenGroup.second)

    with pytest.raises(FinalizerError, match="Errors during sync cleanup") as exc:
        app_container.close_sync()
    assert exc.value.is_async is False
    assert len(exc.value.exceptions) == 1

    assert cleaned_up == ["done"]


async def test_async_finalizer_exception_does_not_abort_remaining_cleanup() -> None:
    cleaned_up: list[str] = []

    async def failing_finalizer(_: SimpleCreator) -> None:
        msg = "async finalizer failed"
        raise RuntimeError(msg)

    async def good_finalizer(_: SimpleCreator) -> None:
        cleaned_up.append("done")

    class BrokenAsyncGroup(Group):
        first = providers.Factory(
            creator=SimpleCreator,
            kwargs={"dep1": "first"},
            cache=providers.CacheSettings(finalizer=failing_finalizer),
        )
        second = providers.Factory(
            creator=SimpleCreator,
            bound_type=None,
            kwargs={"dep1": "second"},
            cache=providers.CacheSettings(finalizer=good_finalizer),
        )

    app_container = Container(groups=[BrokenAsyncGroup])
    app_container.resolve_provider(BrokenAsyncGroup.first)
    app_container.resolve_provider(BrokenAsyncGroup.second)

    with pytest.raises(FinalizerError, match="Errors during async cleanup") as exc:
        await app_container.close_async()
    assert exc.value.is_async is True
    assert len(exc.value.exceptions) == 1

    assert cleaned_up == ["done"]


def _raise_value_error(_: SimpleCreator) -> None:
    msg = "boom"
    raise ValueError(msg)


class _ValueErrorFinalizerGroup(Group):
    failing = providers.Factory(
        creator=SimpleCreator,
        kwargs={"dep1": "x"},
        cache=providers.CacheSettings(finalizer=_raise_value_error),
    )


def test_finalizer_error_is_an_exception_group() -> None:
    container = Container(groups=[_ValueErrorFinalizerGroup])
    container.resolve_provider(_ValueErrorFinalizerGroup.failing)

    with pytest.raises(FinalizerError) as exc_info:
        container.close_sync()

    err = exc_info.value
    assert isinstance(err, ExceptionGroup)
    assert isinstance(err, ModernDIError)
    assert isinstance(err, RuntimeError)
    assert len(err.exceptions) == 1
    assert isinstance(err.exceptions[0], ValueError)
    assert str(err) == (
        "Errors during sync cleanup: [ValueError('boom')]\n"
        "See: https://modern-di.modern-python.org/troubleshooting/finalizer-error/"
    )


def test_except_star_catches_user_finalizer_error_from_close_sync() -> None:
    container = Container(groups=[_ValueErrorFinalizerGroup])
    container.resolve_provider(_ValueErrorFinalizerGroup.failing)
    caught: list[ExceptionGroup[ValueError]] = []

    try:
        container.close_sync()
    except* ValueError as group:
        caught.append(group)

    assert len(caught) == 1
    assert isinstance(caught[0], FinalizerError)
    assert caught[0].is_async is False
    assert [str(e) for e in caught[0].exceptions] == ["boom"]


async def test_except_star_catches_user_finalizer_error_from_close_async() -> None:
    container = Container(groups=[_ValueErrorFinalizerGroup])
    container.resolve_provider(_ValueErrorFinalizerGroup.failing)
    caught: list[ExceptionGroup[ValueError]] = []

    try:
        await container.close_async()
    except* ValueError as group:
        caught.append(group)

    assert len(caught) == 1
    assert isinstance(caught[0], FinalizerError)
    assert caught[0].is_async is True


async def test_except_star_catches_async_finalizer_in_sync_close() -> None:
    app_container = Container(groups=[MyGroup])
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    request_container.resolve_provider(MyGroup.request_cached)
    caught: list[ExceptionGroup[AsyncFinalizerInSyncCloseError]] = []

    try:
        request_container.close_sync()
    except* AsyncFinalizerInSyncCloseError as group:
        caught.append(group)

    assert len(caught) == 1
    (inner,) = caught[0].exceptions
    assert isinstance(inner, AsyncFinalizerInSyncCloseError)
    assert inner.finalizer_type is DependentCreator
    await request_container.close_async()


def test_finalizer_error_split_keeps_type_and_is_async() -> None:
    value_error = ValueError("boom")
    key_error = KeyError("k")
    err = FinalizerError(finalizer_errors=[value_error, key_error], is_async=True)

    matched, rest = err.split(ValueError)

    assert isinstance(matched, FinalizerError)
    assert isinstance(rest, FinalizerError)
    assert matched.is_async is True
    assert rest.is_async is True
    assert matched.exceptions == (value_error,)
    assert rest.exceptions == (key_error,)


def test_finalizer_runs_for_falsy_cached_resource_sync() -> None:
    cleaned_up: list[object] = []

    def collect(value: object) -> None:
        cleaned_up.append(value)

    class FalsyGroup(Group):
        empty_dict = providers.Factory(
            creator=dict,
            cache=providers.CacheSettings(finalizer=collect),
        )

    app_container = Container(groups=[FalsyGroup])
    instance = app_container.resolve_provider(FalsyGroup.empty_dict)
    assert instance == {}

    app_container.close_sync()
    assert cleaned_up == [{}]


async def test_finalizer_runs_for_falsy_cached_resource_async() -> None:
    cleaned_up: list[object] = []

    async def collect(value: object) -> None:
        cleaned_up.append(value)

    class FalsyGroup(Group):
        empty_list = providers.Factory(
            creator=list,
            cache=providers.CacheSettings(finalizer=collect),
        )

    app_container = Container(groups=[FalsyGroup])
    instance = app_container.resolve_provider(FalsyGroup.empty_list)
    assert instance == []

    await app_container.close_async()
    assert cleaned_up == [[]]


def test_cached_none_is_returned_and_finalized() -> None:
    """A creator that returns ``None`` should be treated as a real cached value."""
    call_count = 0
    cleaned_up: list[object] = []

    def create_none() -> None:
        nonlocal call_count
        call_count += 1

    def collect(value: object) -> None:
        cleaned_up.append(value)

    class NoneGroup(Group):
        none_resource = providers.Factory(
            creator=create_none,
            cache=providers.CacheSettings(finalizer=collect),
        )

    app_container = Container(groups=[NoneGroup])
    app_container.resolve_provider(NoneGroup.none_resource)
    app_container.resolve_provider(NoneGroup.none_resource)

    assert call_count == 1  # cached after first call, not re-created
    assert app_container._cache_registry.cached_count() == 1

    app_container.close_sync()
    assert cleaned_up == [None]


class _Conn: ...


class _Svc:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn


class _CountingRLock:
    """An RLock that counts the threads blocked in `acquire`, so a test can wait for contention."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = threading.Condition()
        self.waiting = 0

    def __enter__(self) -> None:
        with self._state:
            self.waiting += 1
            self._state.notify_all()
        self._lock.acquire()
        with self._state:
            self.waiting -= 1

    def __exit__(self, *_: object) -> None:
        self._lock.release()

    def wait_for_waiters(self, count: int) -> bool:
        with self._state:
            return self._state.wait_for(lambda: self.waiting >= count, timeout=5)


def test_concurrent_cache_misses_build_the_value_and_its_dependencies_once() -> None:
    """Threads that miss a cached `Svc(conn: Conn)` together build one Svc and one transient Conn.

    The first Conn build waits until every other thread is blocked on the item's lock, so a
    dependency resolved outside that lock would be built once per thread and fail the count.
    """
    n = 8
    conns: list[_Conn] = []
    lock = _CountingRLock()

    def make_conn() -> _Conn:
        conn = _Conn()
        conns.append(conn)
        if len(conns) == 1:
            lock.wait_for_waiters(n - 1)
        return conn

    class G(Group):
        conn = providers.Factory(creator=make_conn)
        svc = providers.Factory(creator=_Svc, cache=True)

    container = Container(groups=[G])
    container._cache_registry.fetch_cache_item(G.svc).lock = lock  # ty: ignore[invalid-assignment]
    barrier = threading.Barrier(n, timeout=5)

    def worker() -> _Svc:
        barrier.wait()
        return container.resolve(_Svc)

    with ThreadPoolExecutor(max_workers=n) as pool:
        results = [f.result(timeout=10) for f in [pool.submit(worker) for _ in range(n)]]

    assert len(conns) == 1
    assert all(result is results[0] for result in results)
    assert results[0].conn is conns[0]


class _Blocked: ...


class _Free: ...


def test_unrelated_cached_items_are_created_concurrently() -> None:
    """One cached creator blocked mid-creation does not block another item's creation."""
    started = threading.Event()
    release = threading.Event()

    def make_blocked() -> _Blocked:
        started.set()
        release.wait(timeout=5)
        return _Blocked()

    class G(Group):
        blocked = providers.Factory(creator=make_blocked, cache=True)
        free = providers.Factory(creator=_Free, cache=True)

    container = Container(groups=[G])
    blocked = threading.Thread(target=container.resolve, args=(_Blocked,), daemon=True)
    blocked.start()
    try:
        assert started.wait(timeout=5)
        free: list[_Free] = []
        worker = threading.Thread(target=lambda: free.append(container.resolve(_Free)), daemon=True)
        worker.start()
        worker.join(timeout=5)
        assert not worker.is_alive(), "creating one cached item waited for another item's creation"
    finally:
        release.set()
        blocked.join(timeout=5)
    assert isinstance(free[0], _Free)


class _OnWorker: ...


class _ViaWorker:
    def __init__(self, inner: _OnWorker) -> None:
        self.inner = inner


def test_cached_creator_resolving_a_cached_type_on_another_thread_completes() -> None:
    """A cached creator may hand a resolve of another cached type to a worker thread and wait for it."""
    pool = ThreadPoolExecutor(max_workers=1)

    def make_via_worker(container: Container) -> _ViaWorker:
        return _ViaWorker(pool.submit(lambda: container.resolve(_OnWorker)).result(timeout=5))

    class G(Group):
        on_worker = providers.Factory(creator=_OnWorker, cache=True)
        via_worker = providers.Factory(creator=make_via_worker, cache=True)

    container = Container(groups=[G])
    try:
        result = container.resolve(_ViaWorker)
    finally:
        pool.shutdown(wait=False)
    assert result.inner is container.resolve(_OnWorker)


_lifo_events: list[str] = []


class _LifoLeaf: ...


class _LifoMid:
    def __init__(self, leaf: _LifoLeaf) -> None:
        self.leaf = leaf


class _LifoTop:
    def __init__(self, mid: _LifoMid) -> None:
        self.mid = mid


class _LifoGroup(Group):
    leaf = providers.Factory(
        scope=Scope.APP,
        creator=_LifoLeaf,
        cache=providers.CacheSettings(finalizer=lambda _: _lifo_events.append("leaf")),
    )
    mid = providers.Factory(
        scope=Scope.APP,
        creator=_LifoMid,
        cache=providers.CacheSettings(finalizer=lambda _: _lifo_events.append("mid")),
    )
    top = providers.Factory(
        scope=Scope.APP,
        creator=_LifoTop,
        cache=providers.CacheSettings(finalizer=lambda _: _lifo_events.append("top")),
    )


def test_finalizers_run_in_reverse_creation_order_even_with_warmup() -> None:
    _lifo_events.clear()
    container = Container(scope=Scope.APP, groups=[_LifoGroup])
    container.resolve(_LifoLeaf)  # the docs-recommended warmup pattern
    container.resolve(_LifoTop)
    container.close_sync()
    assert _lifo_events == ["top", "mid", "leaf"]


def test_cached_resolution_is_reentrant() -> None:
    class Inner:
        pass

    class Outer:
        def __init__(self, container: Container) -> None:
            self.inner = container.resolve(Inner)

    class ReentrantGroup(Group):
        inner = providers.Factory(creator=Inner, cache=True)
        outer = providers.Factory(creator=Outer, cache=True)

    container = Container(groups=[ReentrantGroup])
    result: list[Outer] = []

    # Use a daemon Thread (not ThreadPoolExecutor) so the worker can be abandoned
    # if it deadlocks — ThreadPoolExecutor.__exit__ would otherwise hang on shutdown
    # waiting for the deadlocked worker to finish.
    def worker() -> None:
        result.append(container.resolve(Outer))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout=5)

    assert not thread.is_alive(), "container.resolve deadlocked: the cache lock is not re-entrant"
    assert len(result) == 1
    assert isinstance(result[0], Outer)
    assert isinstance(result[0].inner, Inner)


_awaitable_fin_events: list[str] = []


class _AwaitableFinSvc: ...


async def _real_cleanup(_: _AwaitableFinSvc) -> None:
    _awaitable_fin_events.append("cleaned")


class _AwaitableFinGroup(Group):
    svc = providers.Factory(
        scope=Scope.APP,
        creator=_AwaitableFinSvc,
        cache=providers.CacheSettings(finalizer=lambda obj: _real_cleanup(obj)),  # noqa: PLW0108
    )


async def test_sync_finalizer_returning_awaitable_is_awaited_in_async_close() -> None:
    _awaitable_fin_events.clear()
    container = Container(scope=Scope.APP, groups=[_AwaitableFinGroup])
    container.resolve(_AwaitableFinSvc)
    await container.close_async()
    assert _awaitable_fin_events == ["cleaned"]


async def test_sync_finalizer_returning_awaitable_raises_in_sync_close_then_recovers() -> None:
    _awaitable_fin_events.clear()
    container = Container(scope=Scope.APP, groups=[_AwaitableFinGroup])
    container.resolve(_AwaitableFinSvc)
    with pytest.raises(FinalizerError):
        container.close_sync()
    assert _awaitable_fin_events == []  # nothing silently dropped
    await container.close_async()  # recovery: async close finalizes the retained cache
    assert _awaitable_fin_events == ["cleaned"]


async def test_sync_finalizer_returning_a_future_raises_in_sync_close_then_recovers() -> None:
    """A future is awaitable but is not a coroutine, so sync close rejects it without closing anything."""
    future: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    class G(Group):
        svc = providers.Factory(
            scope=Scope.APP, creator=_AwaitableFinSvc, cache=providers.CacheSettings(finalizer=lambda _: future)
        )

    container = Container(scope=Scope.APP, groups=[G])
    container.resolve(_AwaitableFinSvc)
    with pytest.raises(FinalizerError) as exc:
        container.close_sync()
    (inner,) = exc.value.exceptions
    assert isinstance(inner, AsyncFinalizerInSyncCloseError)
    assert inner.finalizer_type is _AwaitableFinSvc
    assert container._cache_registry.cached_count() == 1
    future.set_result(None)
    await container.close_async()
    assert container._cache_registry.cached_count() == 0


class _First: ...


class _Second: ...


class _Built:
    count = 0

    def __init__(self) -> None:
        _Built.count += 1


def test_resolve_from_a_finalizer_during_close_sync_raises_container_closed() -> None:
    container = Container()
    _Built.count = 0
    errors: list[Exception] = []

    def resolve_built(_: _First) -> None:
        try:
            container.resolve(_Built)
        except ContainerClosedError as exc:
            errors.append(exc)

    class FinGroup(Group):
        first = providers.Factory(creator=_First, cache=providers.CacheSettings(finalizer=resolve_built))
        built = providers.Factory(creator=_Built, cache=True)

    container.add_providers(FinGroup.first, FinGroup.built)
    container.resolve(_First)
    container.resolve(_Built)

    container.close_sync()

    assert len(errors) == 1
    assert _Built.count == 1
    assert container._cache_registry.cached_count() == 0
    assert container.closed is True


async def test_resolve_from_a_finalizer_during_close_async_raises_container_closed() -> None:
    container = Container()
    _Built.count = 0
    errors: list[Exception] = []

    async def resolve_built(_: _First) -> None:
        try:
            container.resolve(_Built)
        except ContainerClosedError as exc:
            errors.append(exc)

    class FinGroup(Group):
        first = providers.Factory(creator=_First, cache=providers.CacheSettings(finalizer=resolve_built))
        built = providers.Factory(creator=_Built, cache=True)

    container.add_providers(FinGroup.first, FinGroup.built)
    container.resolve(_First)
    container.resolve(_Built)

    await container.close_async()

    assert len(errors) == 1
    assert _Built.count == 1
    assert container._cache_registry.cached_count() == 0
    assert container.closed is True


def _failing_finalizer(_: _First) -> None:
    msg = "boom"
    raise ValueError(msg)


async def _failing_async_finalizer(_: _First) -> None:
    msg = "boom"
    raise ValueError(msg)


def test_failed_sync_finalizer_drops_the_instance() -> None:
    class FailGroup(Group):
        first = providers.Factory(creator=_First, cache=providers.CacheSettings(finalizer=_failing_finalizer))

    container = Container(groups=[FailGroup])
    stale = container.resolve(_First)

    with pytest.raises(FinalizerError) as exc:
        container.close_sync()

    assert [type(e) for e in exc.value.exceptions] == [ValueError]
    assert container._cache_registry.cached_count() == 0
    container.open()
    assert container.resolve(_First) is not stale


async def test_failed_async_finalizer_drops_the_instance() -> None:
    class FailGroup(Group):
        first = providers.Factory(creator=_First, cache=providers.CacheSettings(finalizer=_failing_async_finalizer))

    container = Container(groups=[FailGroup])
    stale = container.resolve(_First)

    with pytest.raises(FinalizerError) as exc:
        await container.close_async()

    assert [type(e) for e in exc.value.exceptions] == [ValueError]
    assert container._cache_registry.cached_count() == 0
    container.open()
    assert container.resolve(_First) is not stale


async def test_cancelled_close_async_keeps_unfinalized_items_queued() -> None:
    events: list[str] = []
    slow_calls: list[int] = []

    def sync_finalizer(_: _First) -> None:
        events.append("first")

    async def slow_finalizer(_: _Second) -> None:
        slow_calls.append(len(slow_calls))
        if len(slow_calls) == 1:
            await asyncio.Event().wait()
        events.append("second")

    class SlowGroup(Group):
        first = providers.Factory(creator=_First, cache=providers.CacheSettings(finalizer=sync_finalizer))
        second = providers.Factory(creator=_Second, cache=providers.CacheSettings(finalizer=slow_finalizer))

    container = Container(groups=[SlowGroup])
    container.resolve(_First)
    container.resolve(_Second)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(container.close_async(), timeout=0.05)

    assert container.closed is True
    assert events == []
    assert slow_calls == [0]

    await container.close_async()

    assert events == ["second", "first"]
    assert slow_calls == [0, 1]
    assert container._cache_registry.cached_count() == 0
