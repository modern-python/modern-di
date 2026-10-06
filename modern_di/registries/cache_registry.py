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
            if self.settings._is_async_finalizer:  # noqa: SLF001
                raise exceptions.AsyncFinalizerInSyncCloseError(instance_type=type(self.cache))
            try:
                result = finalizer(self.cache)
            except Exception:
                self.clear()
                raise
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()  # suppress "never awaited" warning
                raise exceptions.AsyncFinalizerInSyncCloseError(instance_type=type(self.cache))
            self.finalized = True

        self.clear()


def fetch_cache_item(items: dict[int, CacheItem], provider: Factory[typing.Any]) -> CacheItem:
    """Return the cache item in ``items`` for a cached ``provider``, creating it on first use."""
    # Get before setdefault: a bare setdefault builds a throwaway CacheItem on every hit.
    provider_id = provider._provider_id  # noqa: SLF001
    item = items.get(provider_id)
    if item is not None:
        return item
    settings = typing.cast("CacheSettings[typing.Any]", provider._cache_settings)  # noqa: SLF001
    return items.setdefault(provider_id, CacheItem(settings=settings))


async def close_async(creation_order: list[CacheItem]) -> None:
    """Close every item newest first and empty ``creation_order``; failures raise together at the end."""
    finalizer_errors: list[Exception] = []
    for cache_item in reversed(creation_order):
        if cache_item.settings.finalizer is None:
            cache_item.clear()
            continue
        try:
            await cache_item.close_async()
        except Exception as e:  # noqa: BLE001
            finalizer_errors.append(e)
    creation_order.clear()
    if finalizer_errors:
        raise exceptions.FinalizerError(finalizer_errors=finalizer_errors, is_async=True)


def close_sync(creation_order: list[CacheItem]) -> None:
    """Close every item newest first; an async finalizer stays in ``creation_order`` for a later async close."""
    finalizer_errors: list[Exception] = []
    remaining: list[CacheItem] = []
    for cache_item in reversed(creation_order):
        try:
            cache_item.close_sync()
        except exceptions.AsyncFinalizerInSyncCloseError as e:
            finalizer_errors.append(e)
            remaining.append(cache_item)
        except Exception as e:  # noqa: BLE001
            finalizer_errors.append(e)
    remaining.reverse()
    creation_order[:] = remaining
    if finalizer_errors:
        raise exceptions.FinalizerError(finalizer_errors=finalizer_errors, is_async=False)
