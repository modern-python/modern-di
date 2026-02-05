# Migration Guide: Upgrading to modern-di 2.x

This document describes the changes required to migrate from modern-di 1.x versions to modern-di 2.x.

## Overview

The migration to modern-di 2.x involves several key changes in the API, including:
- Simplified container architecture with a single `Container` class
- Updated provider API with keyword-only arguments
- Removal of several provider types (`Singleton`, `Resource`, `Dict`, `List`)
- Changes in caching mechanism
- Updated integration packages

## Key Changes

### 1. Container Changes

The `AsyncContainer` and `SyncContainer` classes have been merged into a single `Container` class. The new container supports both synchronous and asynchronous operations.

**Before (1.x):**
```python
from modern_di import AsyncContainer, SyncContainer

# Asynchronous container
async_container = AsyncContainer(groups=ALL_GROUPS)
async_container.enter()

# Synchronous container
sync_container = SyncContainer(groups=ALL_GROUPS)
sync_container.enter()
```

**After (2.x):**
```python
from modern_di import Container

# Single container for both sync and async operations
container = Container(groups=ALL_GROUPS)
# No need to explicitly enter the container

# For async cleanup
await container.close_async()

# For sync cleanup
container.close_sync()
```

### 2. Provider API Changes

All providers now use keyword-only arguments for better clarity and consistency.

**Before (1.x):**
```python
from modern_di import Scope, providers


factory = providers.Factory(Scope.REQUEST, MyClass, arg1="value1", arg2="value2")
```

**After (2.x):**
```python
from modern_di import Scope, providers


factory = providers.Factory(scope=Scope.REQUEST, creator=MyClass, kwargs={"arg1": "value1", "arg2": "value2"})
```

### 3. Removed Provider Types

Several provider types have been removed and their functionality consolidated into the `Factory` provider:

#### Singleton Provider

**Before (1.x):**
```python
singleton = providers.Singleton(Scope.APP, create_singleton)
```

**After (2.x):**
```python
# Use Factory with cache settings
singleton = providers.Factory(
    scope=Scope.APP, 
    creator=create_singleton,
    cache_settings=providers.CacheSettings()
)
```

#### Resource Provider

**Before (1.x):**
```python
resource = providers.Resource(Scope.REQUEST, create_resource)
```

**After (2.x):**
```python
# Resources can be replaced with Factory with cache_settings with finalizer defined
resource = providers.Factory(
    scope=Scope.REQUEST,
    creator=create_resource,
    cache_settings=providers.CacheSettings(
        finalizer=lambda resource: resource.close(),
        clear_cache=False
    )
)
```

#### Dict and List Providers

These providers have been removed entirely. Use `Factory` providers with appropriate creator functions instead.

**Before (1.x):**
```python
my_dict = providers.Dict(Scope.REQUEST, key1=provider1, key2=provider2)
my_list = providers.List(Scope.REQUEST, provider1, provider2, provider3)
```

**After (2.x):**
```python
from dataclasses import dataclass
from typing import List

@dataclass
class UserService:
    name: str
    age: int

@dataclass
class AuthService:
    token: str
    expiry: int

# Define providers for UserService and AuthService first
user_service_provider = providers.Factory(creator=UserService)
auth_service_provider = providers.Factory(creator=AuthService)

# For dictionaries
def create_services_dict(user_service: UserService, auth_service: AuthService) -> dict[str, object]:
    return {
        "user": user_service,
        "auth": auth_service
    }

my_dict = providers.Factory(creator=create_services_dict)

# For lists
def create_service_list(user_service: UserService, auth_service: AuthService) -> List[object]:
    return [user_service, auth_service]

my_list = providers.Factory(creator=create_service_list)
```

### 4. Caching Changes

Caching is now handled through `CacheSettings` in `Factory` providers.

**Before (1.x):**
```python
# Singleton was automatically cached
singleton = providers.Singleton(Scope.APP, create_singleton)
```

**After (2.x):**
```python
# Explicit cache settings
singleton = providers.Factory(
    creator=create_singleton,
    cache_settings=providers.CacheSettings()
)

# Cache settings with finalizer
cached_with_cleanup = providers.Factory(
    creator=create_resource,
    cache_settings=providers.CacheSettings(
        finalizer=lambda resource: resource.close(),
        clear_cache=False
    )
)
```

### 5. Container Building and Scoping

Child container creation has changed: context managers have been removed and explicit close methods have been added.

**Before (1.x):**
```python
# Async container
async with container.build_child_container(context=context, scope=Scope.REQUEST) as request_container:
    # Use request_container

# Sync container
with container.build_child_container(context=context, scope=Scope.REQUEST) as request_container:
    # Use request_container
```

**After (2.x):**
```python
# Container building remains the same, but now requires explicit cleanup
request_container = container.build_child_container(context=context, scope=Scope.REQUEST)
# Use request_container

# Cleanup now requires explicit calls:
# For async cleanup
await request_container.close_async()

# For sync cleanup
request_container.close_sync()
```

### 6. Provider Resolution

Resolution methods have been simplified.

**Before (1.x):**
```python
# Async resolution
instance = await container.resolve_provider(provider)
instance = await container.resolve(SomeType)

# Sync resolution
instance = container.sync_resolve_provider(provider)
instance = container.sync_resolve(SomeType)
```

**After (2.x):**
```python
# now resolving is sync only
instance = container.resolve_provider(provider)
instance = container.resolve(SomeType)
```

## Migration Steps

1. **Update Dependencies**: Ensure all modern-di packages are updated to 2.x versions
2. **Update Container Initialization**: Replace `AsyncContainer`/`SyncContainer` with `Container`
3. **Update Provider Definitions**: 
   - Replace positional arguments with keyword arguments
   - Replace `Singleton` and `Resource` with `Factory` using `CacheSettings`
   - Remove `Dict` and `List` providers, replace with `Factory` creators
4. **Update Container Building**: Replace context managers with try/finally blocks
5. **Update Provider Resolution**: Remove `sync_` prefixes and `await` keywords

## Breaking Changes

1. `AsyncContainer` and `SyncContainer` classes removed (use `Container` instead)
2. `Singleton`, `Resource`, `Dict`, and `List` provider types removed
3. All provider constructors now use keyword-only arguments
4. Container building no longer uses context managers
5. Provider resolution methods simplified (no `sync_` prefix)
6. Integration packages updated with new APIs
7. Automatic container entry/exit removed (manual cleanup required)
8. Provider casting mechanism changed (`.cast` attribute removed)
