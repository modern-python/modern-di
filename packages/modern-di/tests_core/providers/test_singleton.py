import dataclasses
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
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
    assert cache_item.cache

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

    with pytest.warns(RuntimeWarning, match="Calling `close_sync` for async finalizer"):
        request_container.close_sync()

    assert cache_item.cache
    await request_container.close_async()

    assert cache_item.cache is None


def test_app_singleton_in_request_scope() -> None:
    app_container = Container(groups=[MyGroup])
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    singleton1 = request_container.resolve_provider(MyGroup.app_singleton)

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    singleton2 = request_container.resolve_provider(MyGroup.app_singleton)

    assert singleton1 is singleton2


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
