import dataclasses
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import AsyncFinalizerInSyncCloseError, FinalizerError
from modern_di.types import UNSET


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class DependentCreator:
    dep1: SimpleCreator


def sync_finalizer(_: SimpleCreator) -> None:
    pass


async def async_finalizer(_: DependentCreator) -> None:
    pass


class MyGroup(Group):
    app_singleton = providers.Factory(
        creator=SimpleCreator,
        kwargs={"dep1": "original"},
        cache_settings=providers.CacheSettings(clear_cache=False, finalizer=sync_finalizer),
    )
    request_singleton = providers.Factory(
        scope=Scope.REQUEST, creator=DependentCreator, cache_settings=providers.CacheSettings(finalizer=async_finalizer)
    )


async def test_app_singleton() -> None:
    app_container = Container(groups=[MyGroup])
    singleton1 = app_container.resolve_provider(MyGroup.app_singleton)
    singleton2 = app_container.resolve_provider(MyGroup.app_singleton)
    assert singleton1 is singleton2
    app_container.close_sync()
    cache_item = app_container.cache_registry.fetch_cache_item(MyGroup.app_singleton)
    assert cache_item.cache is not UNSET

    app_container.resolve_provider(MyGroup.app_singleton)
    await app_container.close_async()


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
            cache_settings=providers.CacheSettings(finalizer=failing_finalizer),
        )
        second = providers.Factory(
            creator=SimpleCreator,
            bound_type=None,
            kwargs={"dep1": "second"},
            cache_settings=providers.CacheSettings(finalizer=good_finalizer),
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
            cache_settings=providers.CacheSettings(finalizer=failing_finalizer),
        )
        second = providers.Factory(
            creator=SimpleCreator,
            bound_type=None,
            kwargs={"dep1": "second"},
            cache_settings=providers.CacheSettings(finalizer=good_finalizer),
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
            cache_settings=providers.CacheSettings(finalizer=collect),
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
            cache_settings=providers.CacheSettings(finalizer=collect),
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
            cache_settings=providers.CacheSettings(finalizer=collect),
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

    singleton = providers.Factory(creator=create_singleton, cache_settings=providers.CacheSettings())

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


def test_singleton_resolution_is_reentrant() -> None:
    class Inner:
        pass

    class Outer:
        def __init__(self, container: Container) -> None:
            self.inner = container.resolve(Inner)

    class ReentrantGroup(Group):
        inner = providers.Factory(creator=Inner, cache_settings=providers.CacheSettings())
        outer = providers.Factory(creator=Outer, cache_settings=providers.CacheSettings())

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
