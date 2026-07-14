import threading
import typing

from modern_di.registries.cache_registry import CacheItem


def _item() -> CacheItem:
    return CacheItem(settings=None)


def test_get_or_create_miss_calls_resolve_and_create_once_and_caches() -> None:
    item = _item()
    calls = {"resolve": 0, "create": 0}

    def resolve() -> dict[str, typing.Any]:
        calls["resolve"] += 1
        return {"x": 1}

    def create(kwargs: dict[str, typing.Any]) -> tuple[str, dict[str, typing.Any]]:
        calls["create"] += 1
        return ("made", kwargs)

    value, created = item.get_or_create(None, resolve=resolve, create=create)

    assert created is True
    assert value == ("made", {"x": 1})
    assert item.cache == ("made", {"x": 1})
    assert calls == {"resolve": 1, "create": 1}


def test_get_or_create_hit_returns_cache_without_resolving() -> None:
    item = _item()
    item.cache = "cached"

    def resolve() -> object:  # pragma: no cover
        msg = "resolve must not run on a cache hit"
        raise AssertionError(msg)

    def create(_: object) -> str:  # pragma: no cover
        msg = "create must not run on a cache hit"
        raise AssertionError(msg)

    value, created = item.get_or_create(None, resolve=resolve, create=create)

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

    def create(kwargs: dict[str, typing.Any]) -> str:  # pragma: no cover
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

    # The lock was released by the first call's finally (not left held).
    assert lock.acquire(blocking=False)
    lock.release()
