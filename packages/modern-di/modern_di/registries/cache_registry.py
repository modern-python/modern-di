import dataclasses
import typing
import warnings

from modern_di import types
from modern_di.providers import CacheSettings, Factory


@dataclasses.dataclass(kw_only=True, slots=True)
class CacheItem:
    settings: CacheSettings[typing.Any] | None
    cache: typing.Any | None = None
    kwargs: dict[str, typing.Any] | None = None

    def _clear(self) -> None:
        if self.settings and self.settings.clear_cache:
            self.cache = None

        self.kwargs = None

    async def close_async(self) -> None:
        if self.cache and self.settings and self.settings.finalizer:
            if self.settings.is_async_finalizer:
                await self.settings.finalizer(self.cache)  # type: ignore[misc]
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


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class CacheRegistry:
    _items: dict[str, CacheItem] = dataclasses.field(init=False, default_factory=dict)

    def fetch_cache_item(self, provider: Factory[types.T_co]) -> CacheItem:
        return self._items.setdefault(provider.provider_id, CacheItem(settings=provider.cache_settings))

    async def close_async(self) -> None:
        for cache_item in self._items.values():
            await cache_item.close_async()

    def close_sync(self) -> None:
        for cache_item in self._items.values():
            cache_item.close_sync()
