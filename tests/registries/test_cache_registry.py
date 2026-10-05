import threading
import typing

import pytest

from modern_di.providers import CacheSettings
from modern_di.registries.cache_registry import CacheItem, CacheRegistry
from modern_di.types import UNSET


def _item() -> CacheItem:
    return CacheItem(settings=CacheSettings())


def test_get_or_create_miss_calls_resolve_and_create_once_and_caches() -> None:
    item = _item()
    calls = {"resolve": 0, "create": 0}

    def resolve() -> dict[str, typing.Any]:
        calls["resolve"] += 1
        return {"x": 1}

    def create(kwargs: dict[str, typing.Any]) -> tuple[str, dict[str, typing.Any]]:
        calls["create"] += 1
        return ("made", kwargs)

    value, created = item.get_or_create(threading.RLock(), resolve=resolve, create=create)

    assert created is True
    assert value == ("made", {"x": 1})
    assert item.cache == ("made", {"x": 1})
    assert calls == {"resolve": 1, "create": 1}


def test_get_or_create_hit_returns_cache_without_resolving() -> None:
    item = _item()
    item.cache = "cached"

    def resolve() -> object:  # pragma: no cover - a cache hit must not resolve
        msg = "resolve must not run on a cache hit"
        raise AssertionError(msg)

    def create(_: object) -> str:  # pragma: no cover - a cache hit must not create
        msg = "create must not run on a cache hit"
        raise AssertionError(msg)

    value, created = item.get_or_create(threading.RLock(), resolve=resolve, create=create)

    assert created is False
    assert value == "cached"


def test_get_or_create_double_checks_after_lock() -> None:
    # The inner re-check fires when the cache is UNSET at the fast read but SET
    # by the time the lock is held (a losing thread in production). Simulate it
    # deterministically: resolve() sets the cache as a side effect, so the
    # post-lock re-check must return it and skip create.
    item = _item()
    created_calls: list[object] = []

    def resolve() -> dict[str, typing.Any]:
        item.cache = "won-the-race"
        return {}

    def create(kwargs: dict[str, typing.Any]) -> str:  # pragma: no cover - the post-lock re-check must skip create
        created_calls.append(kwargs)
        return "should-not-be-used"

    value, created = item.get_or_create(threading.RLock(), resolve=resolve, create=create)

    assert created is False
    assert value == "won-the-race"
    assert created_calls == []


def test_get_or_create_releases_lock_and_fast_path_on_second_call() -> None:
    item = _item()
    lock = threading.RLock()

    value, created = item.get_or_create(lock, resolve=lambda: 0, create=lambda _: "v")
    assert (value, created) == ("v", True)

    # Second call hits the fast path (cache set) — returns before touching the lock.
    value2, created2 = item.get_or_create(lock, resolve=lambda: 0, create=lambda _: "v2")
    assert (value2, created2) == ("v", False)

    acquired: list[bool] = []

    def try_acquire() -> None:
        acquired.append(lock.acquire(blocking=False))

    thread = threading.Thread(target=try_acquire)
    thread.start()
    thread.join()
    assert acquired == [True]


async def test_close_async_awaits_only_items_with_a_finalizer(monkeypatch: pytest.MonkeyPatch) -> None:
    awaited: list[CacheItem] = []
    original = CacheItem.close_async

    async def _recording(self: CacheItem) -> None:
        awaited.append(self)
        await original(self)

    monkeypatch.setattr(CacheItem, "close_async", _recording)
    finalized: list[object] = []
    registry = CacheRegistry()
    plain = CacheItem(settings=CacheSettings(), cache="plain")
    persistent = CacheItem(settings=CacheSettings(clear_cache=False), cache="persistent")
    with_finalizer = CacheItem(settings=CacheSettings(finalizer=finalized.append), cache="finalized")
    for item in (plain, persistent, with_finalizer):
        registry.mark_created(item)

    await registry.close_async()

    assert awaited == [with_finalizer]
    assert finalized == ["finalized"]
    assert plain.cache is UNSET
    assert persistent.cache == "persistent"
    assert registry._creation_order == []
