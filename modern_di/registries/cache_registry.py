import dataclasses
import inspect
import typing

from modern_di import exceptions, types
from modern_di.providers import CacheSettings, Factory


@dataclasses.dataclass(kw_only=True, slots=True)
class CacheItem:
    settings: CacheSettings[typing.Any] | None
    cache: typing.Any = types.UNSET
    kwargs_compiled: bool = False
    finalized: bool = False
    provider_kwargs: dict[str, typing.Any] = dataclasses.field(default_factory=dict)
    static_kwargs: dict[str, typing.Any] = dataclasses.field(default_factory=dict)
    context_kwargs: dict[str, typing.Any] = dataclasses.field(default_factory=dict)

    def _clear(self) -> None:
        if self.settings and self.settings.clear_cache:
            self.cache = types.UNSET
            self.finalized = False

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
