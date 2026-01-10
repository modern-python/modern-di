import dataclasses
import typing

from modern_di import types
from modern_di.providers import CacheSettings, Factory


@dataclasses.dataclass(kw_only=True, slots=True)
class CacheItem:
    settings: CacheSettings[typing.Any] | None
    cache: typing.Any | None = None
    kwargs: dict[str, typing.Any] | None = None


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class CacheRegistry:
    _items: dict[str, CacheItem] = dataclasses.field(init=False, default_factory=dict)

    def fetch_cache_item(self, provider: Factory[types.T_co]) -> CacheItem:
        return self._items.setdefault(provider.provider_id, CacheItem(settings=provider.cache_settings))
