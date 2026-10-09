import threading
import typing
from concurrent.futures import ThreadPoolExecutor

import pytest

from modern_di import Container, Group, Scope
from modern_di.cache import CacheItem, close_async
from modern_di.providers import CacheSettings, Factory
from modern_di.types import UNSET
from tests.helpers import cache_item


def _item() -> CacheItem:
    return CacheItem(settings=CacheSettings())


def _acquirable_from_another_thread(item: CacheItem) -> bool:
    """Whether another thread can take `item`'s lock right now; releases it again if so."""
    acquired: list[bool] = []

    def try_acquire() -> None:
        got = item.lock.acquire(blocking=False)
        if got:
            item.lock.release()
        acquired.append(got)

    thread = threading.Thread(target=try_acquire)
    thread.start()
    thread.join(timeout=5)
    return acquired == [True]


def test_get_or_create_miss_builds_and_creates_once_under_the_item_lock() -> None:
    item = _item()
    calls = {"build": 0, "create": 0}

    def build(_: object) -> dict[str, typing.Any]:
        calls["build"] += 1
        assert not _acquirable_from_another_thread(item)
        return {"x": 1}

    def create(kwargs: dict[str, typing.Any]) -> tuple[str, dict[str, typing.Any]]:
        calls["create"] += 1
        return ("made", kwargs)

    value, created = item.get_or_create(lambda target: create(build(target)), None)

    assert created is True
    assert value == ("made", {"x": 1})
    assert item.cache == ("made", {"x": 1})
    assert calls == {"build": 1, "create": 1}


def test_get_or_create_hit_returns_cache_without_building() -> None:
    item = _item()
    item.cache = "cached"

    def build(_: object) -> object:
        msg = "build must not run on a cache hit"
        raise AssertionError(msg)

    def create(_: object) -> str:
        msg = "create must not run on a cache hit"
        raise AssertionError(msg)

    value, created = item.get_or_create(lambda target: create(build(target)), None)

    assert created is False
    assert value == "cached"


class _LosingRaceLock:
    """Stores a value in the item while the caller waits for the lock, as a winning thread would."""

    def __init__(self, item: CacheItem) -> None:
        self._item = item

    def __enter__(self) -> None:
        self._item.cache = "won-the-race"

    def __exit__(self, *_: object) -> None:
        pass


def test_get_or_create_double_checks_under_the_lock() -> None:
    item = _item()
    item.lock = _LosingRaceLock(item)  # ty: ignore[invalid-assignment]

    def build(_: object) -> object:
        msg = "build must not run when another thread already stored the value"
        raise AssertionError(msg)

    def create(_: object) -> str:
        msg = "create must not run when another thread already stored the value"
        raise AssertionError(msg)

    value, created = item.get_or_create(lambda target: create(build(target)), None)

    assert created is False
    assert value == "won-the-race"


def test_get_or_create_releases_the_item_lock() -> None:
    item = _item()

    value, created = item.get_or_create(lambda _: "v", None)
    assert (value, created) == ("v", True)
    assert _acquirable_from_another_thread(item)


def test_each_cache_item_owns_its_lock() -> None:
    container = Container(scope=Scope.APP)
    first = cache_item(container, Factory(creator=lambda: 1, bound_type=int, cache=True))
    second = cache_item(container, Factory(creator=lambda: "", bound_type=str, cache=True))
    assert first.lock is not second.lock


@pytest.mark.thread_race
def test_concurrent_first_resolves_of_one_provider_build_once() -> None:
    n = 8
    built: list[object] = []

    def make() -> object:
        built.append(value := object())
        return value

    class G(Group):
        cached = Factory(creator=make, bound_type=object, cache=True)

    container = Container(scope=Scope.APP, groups=[G])
    barrier = threading.Barrier(n, timeout=5)

    def resolve() -> object:
        barrier.wait()
        return container.resolve(object)

    with ThreadPoolExecutor(max_workers=n) as pool:
        values = [f.result(timeout=5) for f in [pool.submit(resolve) for _ in range(n)]]

    assert len(built) == 1
    assert all(value is built[0] for value in values)


async def test_close_async_runs_only_owed_finalizers_and_empties_the_order() -> None:
    finalized: list[object] = []
    plain = CacheItem(settings=CacheSettings(), cache="plain")
    persistent = CacheItem(settings=CacheSettings(clear_cache=False), cache="persistent")
    with_finalizer = CacheItem(settings=CacheSettings(finalizer=finalized.append), cache="finalized")
    never_built = CacheItem(settings=CacheSettings(finalizer=finalized.append))
    creation_order = [plain, persistent, with_finalizer, never_built]

    await close_async(creation_order)

    assert finalized == ["finalized"]
    assert plain.cache is UNSET
    assert persistent.cache == "persistent"
    assert with_finalizer.cache is UNSET
    assert creation_order == []
