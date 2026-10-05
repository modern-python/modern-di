import typing

from modern_di import Container
from modern_di.providers import Factory
from modern_di.registries.cache_registry import CacheItem


def cache_item(container: Container, provider: Factory[typing.Any]) -> CacheItem:
    """Return `container`'s cache item for the cached `provider`, creating it if needed."""
    return container._cache_registry.fetch_cache_item(provider)
