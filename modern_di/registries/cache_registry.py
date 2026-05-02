import dataclasses
import typing
import warnings

from modern_di import exceptions, types
from modern_di.providers import CacheSettings, Factory


@dataclasses.dataclass(kw_only=True, slots=True)
class CacheItem:
    settings: CacheSettings[typing.Any] | None
    cache: typing.Any | None = None
    kwargs_compiled: bool = False
    provider_kwargs: dict[str, typing.Any] = dataclasses.field(default_factory=dict)
    static_kwargs: dict[str, typing.Any] = dataclasses.field(default_factory=dict)

    def _clear(self) -> None:
        if self.settings and self.settings.clear_cache:
            self.cache = None

    async def close_async(self) -> None:
        if self.cache and self.settings and self.settings.finalizer:
            if self.settings.is_async_finalizer:
                await self.settings.finalizer(self.cache)  # ty: ignore[invalid-await]
            else:
                self.settings.finalizer(self.cache)

        self._clear()

    def close_sync(self) -> None:
        if self.cache and self.settings and self.settings.finalizer:
            if self.settings.is_async_finalizer:
                warnings.warn(
                    f"Calling `close_sync` for async finalizer, type={type(self.cache)}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                return
            self.settings.finalizer(self.cache)

        self._clear()


@dataclasses.dataclass(kw_only=True, slots=True)
class CacheRegistry:
    _items: dict[int, CacheItem] = dataclasses.field(init=False, default_factory=dict)

    def cached_count(self) -> int:
        return sum(1 for item in self._items.values() if item.cache is not None)

    def fetch_cache_item(self, provider: Factory[types.T_co]) -> CacheItem:
        return self._items.setdefault(provider.provider_id, CacheItem(settings=provider.cache_settings))

    async def close_async(self) -> None:
        finalizer_errors: list[BaseException] = []
        for cache_item in self._items.values():
            try:
                await cache_item.close_async()
            except Exception as e:  # noqa: BLE001, PERF203
                finalizer_errors.append(e)
        if finalizer_errors:
            raise exceptions.FinalizerError(finalizer_errors=finalizer_errors, is_async=True)

    def close_sync(self) -> None:
        finalizer_errors: list[BaseException] = []
        for cache_item in self._items.values():
            try:
                cache_item.close_sync()
            except Exception as e:  # noqa: BLE001, PERF203
                finalizer_errors.append(e)
        if finalizer_errors:
            raise exceptions.FinalizerError(finalizer_errors=finalizer_errors, is_async=False)
