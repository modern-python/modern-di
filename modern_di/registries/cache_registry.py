import dataclasses
import inspect
import typing

from modern_di import exceptions, types
from modern_di.providers import CacheSettings, Factory


if typing.TYPE_CHECKING:
    import threading


_R = typing.TypeVar("_R")
_V = typing.TypeVar("_V")


@dataclasses.dataclass(kw_only=True, slots=True)
class CacheItem:
    settings: CacheSettings[typing.Any] | None
    cache: typing.Any = types.UNSET
    finalized: bool = False

    def _clear(self) -> None:
        if self.settings and self.settings.clear_cache:
            self.cache = types.UNSET
            self.finalized = False

    def get_or_create(
        self,
        lock: "threading.RLock | None",
        resolve: typing.Callable[[], _R],
        create: typing.Callable[[_R], _V],
    ) -> tuple[_V, bool]:
        """Return the memoized singleton, or resolve-and-create it once under `lock`.

        Two phases: `resolve()` runs unlocked (recursive dependency resolution must not
        hold the lock); creation and the store run under `lock`, double-checked so at
        most one caller creates. `lock` is the resolving container's `RLock` (or None
        when the container was built with `use_lock=False`). Returns `(value, created)`;
        `created` is True only when this call ran `create`.
        """
        if self.cache is not types.UNSET:
            return self.cache, False
        resolved = resolve()
        if lock is not None:
            lock.acquire()
        try:
            if self.cache is not types.UNSET:
                return self.cache, False
            value = create(resolved)
            self.cache = value
            return value, True
        finally:
            if lock is not None:
                lock.release()

    async def close_async(self) -> None:
        if self.cache is not types.UNSET and not self.finalized and self.settings and self.settings.finalizer:
            result = self.settings.finalizer(self.cache)
            if inspect.isawaitable(result):
                await result
            self.finalized = True

        self._clear()

    def close_sync(self) -> None:
        if self.cache is not types.UNSET and not self.finalized and self.settings and self.settings.finalizer:
            if self.settings.is_async_finalizer:
                raise exceptions.AsyncFinalizerInSyncCloseError(finalizer_type=type(self.cache))
            result = self.settings.finalizer(self.cache)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()  # suppress "never awaited" warning
                raise exceptions.AsyncFinalizerInSyncCloseError(finalizer_type=type(self.cache))
            self.finalized = True

        self._clear()


@dataclasses.dataclass(kw_only=True, slots=True)
class CacheRegistry:
    _items: dict[int, CacheItem] = dataclasses.field(init=False, default_factory=dict)
    _creation_order: list[CacheItem] = dataclasses.field(init=False, default_factory=list)

    def cached_count(self) -> int:
        return sum(1 for item in self._items.values() if item.cache is not types.UNSET)

    def fetch_cache_item(self, provider: Factory[types.T_co]) -> CacheItem:
        # Fast path: return an existing item without building a throwaway CacheItem (plain
        # setdefault eagerly constructs one on every hit). The creation path still uses
        # setdefault so it stays atomic under the GIL — fetch runs outside the container lock,
        # and concurrent first-resolvers must share one CacheItem because the singleton cache
        # and its double-checked lock live on that object.
        item = self._items.get(provider.provider_id)
        if item is not None:
            return item
        return self._items.setdefault(provider.provider_id, CacheItem(settings=provider.cache_settings))

    def mark_created(self, cache_item: CacheItem) -> None:
        """Record creation completion; close finalizes in reverse of this order (LIFO)."""
        self._creation_order.append(cache_item)

    async def close_async(self) -> None:
        finalizer_errors: list[BaseException] = []
        for cache_item in reversed(self._creation_order):
            try:
                await cache_item.close_async()
            except Exception as e:  # noqa: BLE001, PERF203
                finalizer_errors.append(e)
        self._creation_order.clear()
        if finalizer_errors:
            raise exceptions.FinalizerError(finalizer_errors=finalizer_errors, is_async=True)

    def close_sync(self) -> None:
        finalizer_errors: list[BaseException] = []
        remaining: list[CacheItem] = []
        for cache_item in reversed(self._creation_order):
            try:
                cache_item.close_sync()
            except exceptions.AsyncFinalizerInSyncCloseError as e:  # noqa: PERF203
                finalizer_errors.append(e)
                remaining.append(cache_item)
            except Exception as e:  # noqa: BLE001
                finalizer_errors.append(e)
        remaining.reverse()
        self._creation_order = remaining
        if finalizer_errors:
            raise exceptions.FinalizerError(finalizer_errors=finalizer_errors, is_async=False)
