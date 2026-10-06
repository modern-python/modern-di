import typing

from modern_di import Container
from modern_di.cache import CacheItem, fetch_cache_item
from modern_di.providers import Factory


def cache_item(container: Container, provider: Factory[typing.Any]) -> CacheItem:
    """Return `container`'s cache item for the cached `provider`, creating it if needed."""
    return fetch_cache_item(container._cache_items, provider)
