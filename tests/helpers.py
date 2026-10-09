import typing

from modern_di import Container
from modern_di.cache import CacheItem
from modern_di.providers import CacheSettings, Factory


def cache_item(container: Container, provider: Factory[typing.Any]) -> CacheItem:
    """Return `container`'s cache item for the cached `provider`, creating it if needed."""
    settings = typing.cast("CacheSettings[typing.Any]", provider.cache_settings)
    return container._cache_items.setdefault(provider.provider_id, CacheItem(settings=settings))
