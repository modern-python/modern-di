import dataclasses
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import AsyncFinalizerInSyncCloseError, ContainerClosedError, FinalizerError
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
    app_singleton = providers.Factory(
        creator=SimpleCreator,
        kwargs={"dep1": "original"},
        cache=True,
    )
    request_singleton = providers.Factory(
        scope=Scope.REQUEST, creator=DependentCreator, cache=providers.CacheSettings(finalizer=async_finalizer)
    )


async def test_app_singleton() -> None:
    sync_calls: list[SimpleCreator] = []

    class LocalGroup(Group):
        singleton = providers.Factory(
            creator=SimpleCreator,
            kwargs={"dep1": "original"},
            cache=providers.CacheSettings(clear_cache=False, finalizer=sync_calls.append),
        )

    app_container = Container(groups=[LocalGroup])
    singleton1 = app_container.resolve_provider(LocalGroup.singleton)
    singleton2 = app_container.resolve_provider(LocalGroup.singleton)
    assert singleton1 is singleton2

    app_container.close_sync()
    assert sync_calls == [singleton1]  # finalizer ran once on close

    with pytest.raises(ContainerClosedError):
        app_container.resolve_provider(LocalGroup.singleton)

    # clear_cache=False: the instance survives the close and is returned again after reopen,
    # without re-running the creator or finalizer (behavioral check, not cache_registry inspection).
    with app_container:
        assert app_container.resolve_provider(LocalGroup.singleton) is singleton1

    await app_container.close_async()
    assert sync_calls == [singleton1]


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


def test_closed_container_refuses_re_resolve_with_clear_cache_true() -> None:
    calls: list[str] = []

    class G(Group):
        f = providers.Factory(
            creator=lambda: "r",
            bound_type=str,
            cache=providers.CacheSettings(clear_cache=True, finalizer=calls.append),
        )

    container = Container(groups=[G])
    container.resolve(str)
    container.close_sync()
    assert calls == ["r"]
    with pytest.raises(ContainerClosedError):
        container.resolve(str)
    container.close_sync()  # close stays idempotent and never re-runs finalizers
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


async def test_request_singleton() -> None:
    app_container = Container(groups=[MyGroup])
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance1 = request_container.resolve_provider(MyGroup.request_singleton)
    instance2 = request_container.resolve(DependentCreator)
    assert isinstance(instance1.dep1, SimpleCreator)
    assert instance1 is instance2

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance3 = request_container.resolve_provider(MyGroup.request_singleton)
    instance4 = request_container.resolve(DependentCreator)
    assert instance3 is instance4
    assert instance1 is not instance3

    cache_item = request_container.cache_registry.fetch_cache_item(MyGroup.request_singleton)

    with pytest.raises(FinalizerError) as exc_info:
        request_container.close_sync()
    assert exc_info.value.is_async is False
    assert len(exc_info.value.finalizer_errors) == 1
    assert isinstance(exc_info.value.finalizer_errors[0], AsyncFinalizerInSyncCloseError)

    assert cache_item.cache is not UNSET  # preserved — user can still recover via close_async
    await request_container.close_async()

    assert cache_item.cache is UNSET


def test_app_singleton_in_request_scope() -> None:
    app_container = Container(groups=[MyGroup])
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    singleton1 = request_container.resolve_provider(MyGroup.app_singleton)

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    singleton2 = request_container.resolve_provider(MyGroup.app_singleton)

    assert singleton1 is singleton2


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
    assert len(exc.value.finalizer_errors) == 1

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
    assert len(exc.value.finalizer_errors) == 1

    assert cleaned_up == ["done"]


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
    assert app_container.cache_registry.cached_count() == 1

    app_container.close_sync()
    assert cleaned_up == [None]


@pytest.mark.repeat(10)
def test_singleton_threading_concurrency() -> None:
    calls: int = 0
    lock = threading.Lock()

    def create_singleton() -> str:
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.01)
        return ""

    singleton = providers.Factory(creator=create_singleton, cache=True)

    def resolve_singleton(container: Container) -> str:
        return container.resolve_provider(singleton)

    app_container = Container()
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [
            pool.submit(resolve_singleton, app_container),
            pool.submit(resolve_singleton, app_container),
            pool.submit(resolve_singleton, app_container),
            pool.submit(resolve_singleton, app_container),
        ]
        results = [x.result() for x in as_completed(tasks)]

    assert all(x == "" for x in results)
    assert calls == 1


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


def test_singleton_resolution_is_reentrant() -> None:
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

    assert not thread.is_alive(), "container.resolve deadlocked — singleton lock is not re-entrant"
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


_cycle_events: list[str] = []


class _PersistentBroker: ...


class _EphemeralSvc: ...


class _CycleGroup(Group):
    broker = providers.Factory(
        scope=Scope.APP,
        creator=_PersistentBroker,
        cache=providers.CacheSettings(clear_cache=False, finalizer=lambda _: _cycle_events.append("broker-finalized")),
    )
    svc = providers.Factory(
        scope=Scope.APP,
        creator=_EphemeralSvc,
        cache=True,  # clear_cache=True default
    )


def test_persistent_provider_survives_close_reopen_cycle() -> None:
    _cycle_events.clear()
    container = Container(scope=Scope.APP, groups=[_CycleGroup])
    with container:
        broker1 = container.resolve(_PersistentBroker)
        svc1 = container.resolve(_EphemeralSvc)
    # exited → closed; finalizer ran once
    assert _cycle_events == ["broker-finalized"]
    # resolving while closed raises
    with pytest.raises(ContainerClosedError):
        container.resolve(_PersistentBroker)
    # re-enter → reopen
    with container:
        broker2 = container.resolve(_PersistentBroker)
        svc2 = container.resolve(_EphemeralSvc)
    assert broker2 is broker1  # persistent: same instance preserved
    assert svc2 is not svc1  # ephemeral: rebuilt fresh
    # finalizer did NOT re-fire for the preserved broker
    assert _cycle_events == ["broker-finalized"]
