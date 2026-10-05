import dataclasses
import inspect
import threading
import typing

from modern_di import exceptions, types
from modern_di.providers import CacheSettings, Factory


_R = typing.TypeVar("_R")
_V = typing.TypeVar("_V")


@dataclasses.dataclass(kw_only=True, slots=True)
class CacheItem:
    settings: CacheSettings[typing.Any]
    cache: typing.Any = types.UNSET
    finalized: bool = False
    lock: threading.RLock = dataclasses.field(default_factory=threading.RLock, repr=False, compare=False)

    def clear(self) -> None:
        if self.settings.clear_cache:
            self.cache = types.UNSET
            self.finalized = False

    def get_or_create(
        self,
        resolve: typing.Callable[[], _R],
        create: typing.Callable[[_R], _V],
    ) -> tuple[_V, bool]:
        """Return the memoized singleton, or resolve-and-create it once under this item's lock.

        A hit never takes the lock. A miss resolves and creates under it, so concurrent misses
        build the value and its dependencies once. `created` is True only for the caller that built.
        """
        if self.cache is not types.UNSET:
            return self.cache, False
        with self.lock:
            if self.cache is not types.UNSET:
                return self.cache, False
            value = create(resolve())
            self.cache = value
            return value, True

    def _pending_finalizer(self) -> typing.Callable[[typing.Any], typing.Awaitable[None] | None] | None:
        """Return the finalizer still owed to the cached value, or None when nothing is owed."""
        return None if self.cache is types.UNSET or self.finalized else self.settings.finalizer

    async def close_async(self) -> None:
        if (finalizer := self._pending_finalizer()) is not None:
            try:
                result = finalizer(self.cache)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                self.clear()
                raise
            self.finalized = True

        self.clear()

    def close_sync(self) -> None:
        if (finalizer := self._pending_finalizer()) is not None:
            if self.settings.is_async_finalizer:
                raise exceptions.AsyncFinalizerInSyncCloseError(finalizer_type=type(self.cache))
            try:
                result = finalizer(self.cache)
            except Exception:
                self.clear()
                raise
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()  # suppress "never awaited" warning
                raise exceptions.AsyncFinalizerInSyncCloseError(finalizer_type=type(self.cache))
            self.finalized = True

        self.clear()


class CacheRegistry:
    __slots__ = ("_creation_order", "_items")

    def __init__(self) -> None:
        self._items: dict[int, CacheItem] = {}
        self._creation_order: list[CacheItem] = []

    def cached_count(self) -> int:
        return sum(1 for item in self._items.values() if item.cache is not types.UNSET)

    def fetch_cache_item(self, provider: Factory[typing.Any]) -> CacheItem:
        """Return the cache item for a cached ``provider``, creating it on first use."""
        # Get before setdefault: a bare setdefault builds a throwaway CacheItem on every hit.
        item = self._items.get(provider.provider_id)
        if item is not None:
            return item
        settings = typing.cast("CacheSettings[typing.Any]", provider.cache_settings)
        return self._items.setdefault(provider.provider_id, CacheItem(settings=settings))

    def mark_created(self, cache_item: CacheItem) -> None:
        """Record creation completion; close finalizes in reverse of this order (LIFO)."""
        self._creation_order.append(cache_item)

    async def close_async(self) -> None:
        finalizer_errors: list[Exception] = []
        for cache_item in reversed(self._creation_order):
            if cache_item.settings.finalizer is None:
                cache_item.clear()
                continue
            try:
                await cache_item.close_async()
            except Exception as e:  # noqa: BLE001
                finalizer_errors.append(e)
        self._creation_order.clear()
        if finalizer_errors:
            raise exceptions.FinalizerError(finalizer_errors=finalizer_errors, is_async=True)

    def close_sync(self) -> None:
        finalizer_errors: list[Exception] = []
        remaining: list[CacheItem] = []
        for cache_item in reversed(self._creation_order):
            try:
                cache_item.close_sync()
            except exceptions.AsyncFinalizerInSyncCloseError as e:
                finalizer_errors.append(e)
                remaining.append(cache_item)
            except Exception as e:  # noqa: BLE001
                finalizer_errors.append(e)
        remaining.reverse()
        self._creation_order = remaining
        if finalizer_errors:
            raise exceptions.FinalizerError(finalizer_errors=finalizer_errors, is_async=False)
