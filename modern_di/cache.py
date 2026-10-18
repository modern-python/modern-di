import inspect
import threading
import typing

from modern_di import exceptions, types
from modern_di.exceptions.lifecycle import finalizer_note
from modern_di.providers import CacheSettings


_T = typing.TypeVar("_T")
_V = typing.TypeVar("_V")


class CacheItem:
    __slots__ = ("cache", "finalized", "lock", "settings")

    def __init__(self, settings: CacheSettings[typing.Any]) -> None:
        self.settings = settings
        self.cache: typing.Any = types.UNSET
        self.finalized = False
        self.lock = threading.RLock()

    def clear(self) -> None:
        if self.settings.clear_cache:
            self.cache = types.UNSET
            self.finalized = False

    def get_or_create(self, make: typing.Callable[[_T], _V], target: _T) -> tuple[_V, bool]:
        """Return the memoized singleton, or ``make(target)`` it once under this item's lock.

        A hit never takes the lock. A miss builds and creates under it, so concurrent misses
        build the value and its dependencies once. `created` is True only for the caller that built.
        """
        if self.cache is not types.UNSET:
            return self.cache, False
        with self.lock:
            if self.cache is not types.UNSET:
                return self.cache, False
            value = make(target)
            self.cache = value
            return value, True


def cached_count(items: dict[int, CacheItem]) -> int:
    """Return how many of ``items`` hold a value."""
    return sum(1 for item in items.values() if item.cache is not types.UNSET)


async def close_async(creation_order: list[CacheItem]) -> None:
    """Pop and close items newest first until ``creation_order`` is empty; failures raise together at the end."""
    finalizer_errors: list[Exception] = []
    while creation_order:
        cache_item = creation_order.pop()
        finalizer = cache_item.settings.finalizer
        if finalizer is not None and cache_item.cache is not types.UNSET and not cache_item.finalized:
            try:
                result = finalizer(cache_item.cache)
                if result is not None and inspect.isawaitable(result):
                    await result
            except Exception as e:  # noqa: BLE001
                e.add_note(finalizer_note(type(cache_item.cache)))
                finalizer_errors.append(e)
            except BaseException:
                creation_order.append(cache_item)
                raise
            else:
                cache_item.finalized = True
        cache_item.clear()
    if finalizer_errors:
        raise exceptions.FinalizerError(exceptions=finalizer_errors, is_async=True)


def close_sync(creation_order: list[CacheItem]) -> None:
    """Pop and close items newest first until ``creation_order`` is empty; an async finalizer is queued again."""
    finalizer_errors: list[Exception] = []
    remaining: list[CacheItem] = []
    while creation_order:
        cache_item = creation_order.pop()
        finalizer = cache_item.settings.finalizer
        value = cache_item.cache
        if finalizer is not None and value is not types.UNSET and not cache_item.finalized:
            if cache_item.settings._is_async_finalizer:  # noqa: SLF001
                finalizer_errors.append(exceptions.AsyncFinalizerInSyncCloseError(instance_type=type(value)))
                remaining.append(cache_item)
                continue
            try:
                result = finalizer(value)
            except Exception as e:  # noqa: BLE001
                e.add_note(finalizer_note(type(value)))
                finalizer_errors.append(e)
            except BaseException:
                creation_order.extend([cache_item, *reversed(remaining)])
                raise
            else:
                if result is not None and inspect.isawaitable(result):
                    if inspect.iscoroutine(result):
                        result.close()  # suppress "never awaited" warning
                    finalizer_errors.append(exceptions.AsyncFinalizerInSyncCloseError(instance_type=type(value)))
                    remaining.append(cache_item)
                    continue
                cache_item.finalized = True
        cache_item.clear()
    remaining.reverse()
    creation_order[:0] = remaining
    if finalizer_errors:
        raise exceptions.FinalizerError(exceptions=finalizer_errors, is_async=False)
