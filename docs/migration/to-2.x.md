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
    )
)
```

`clear_cache` defaults to `True`, which matches the old `Resource` semantics: the
finalizer runs when the container is closed and the instance is rebuilt on the next
resolve. Set `clear_cache=False` only for an instance whose identity must survive a
close→reopen cycle — the cached instance is kept, so the *same object* is returned again
after the container is re-entered (its finalizer runs once and is not re-run on later
closes). Reach for that only when a single shared resource must stay stable across
restarts; for ordinary per-scope resources keep the default.

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

@dataclass(kw_only=True, slots=True, frozen=True)
class UserService:
    name: str
    age: int

@dataclass(kw_only=True, slots=True, frozen=True)
class AuthService:
    token: str
    expiry: int

# Define providers for UserService and AuthService first.
# Primitive fields (str/int) have no provider — supply them via kwargs.
user_service_provider = providers.Factory(creator=UserService, kwargs={"name": "admin", "age": 30})
auth_service_provider = providers.Factory(creator=AuthService, kwargs={"token": "secret", "expiry": 3600})

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
    )
)
```

With the default `clear_cache=True`, the cached instance is finalized when the container
closes and rebuilt on the next resolve. Use `clear_cache=False` only when the same object
must persist across a close→reopen cycle.

### 5. Container Building and Scoping

Child container creation continues to support context managers in 2.x — use `with` / `async with` for automatic cleanup. The explicit `close_sync()` / `close_async()` methods are also available for callers that need to manage the container lifecycle manually.

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
# Same context-manager form continues to work
with container.build_child_container(context=context, scope=Scope.REQUEST) as request_container:
    # Use request_container

async with container.build_child_container(context=context, scope=Scope.REQUEST) as request_container:
    # Use request_container

# If you need manual lifecycle control, call close_sync() or await close_async() yourself
request_container = container.build_child_container(context=context, scope=Scope.REQUEST)
# Use request_container
request_container.close_sync()  # or: await request_container.close_async()
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

!!! note "Async finalizers are still supported"
    Only *resolution* became sync-only in 2.x. Async *finalizers* (cleanup functions) are still fully supported via `CacheSettings(finalizer=async_cleanup_fn)` and `await container.close_async()`. The distinction: you cannot `await` during dependency resolution, but you can use async functions to clean up resources when a container is closed.

### 7. Migrating `.cast`

In 1.x, `.cast` wired one provider into another's dependency, e.g.
`UserService(db_engine=database_engine.cast)`. There is no `.cast` in 2.x — wiring is by type.
Map each 1.x usage:

| 1.x | 2.x |
|---|---|
| `dep=other_provider.cast` (a provider dependency) | Drop the argument — annotate the creator parameter with the dependency's type; it's resolved by type automatically. |
| `value=settings.host` (a static/literal value) | Pass it in `kwargs={"value": ...}`. |
| a request/context value | Register a `ContextProvider` for that type (see [Context](../providers/context.md)). |

```python
# 1.x
service = providers.Factory(MyService, db_engine=database_engine.cast)

# 2.x — MyService.__init__(self, db_engine: DBEngine); db_engine resolved by type
service = providers.Factory(scope=Scope.APP, creator=MyService)
```

## Migration Steps

1. **Update Dependencies**: Ensure all modern-di packages are updated to 2.x versions
2. **Update Container Initialization**: Replace `AsyncContainer`/`SyncContainer` with `Container`
3. **Update Provider Definitions**: 
   - Replace positional arguments with keyword arguments
   - Replace `Singleton` and `Resource` with `Factory` using `CacheSettings`
   - Remove `Dict` and `List` providers, replace with `Factory` creators
4. **Update Container Building**: Continue to use `with` / `async with` for automatic cleanup; `close_sync()` / `close_async()` are also available for manual lifecycle control
5. **Update Provider Resolution**: Remove `sync_` prefixes and `await` keywords

## Breaking Changes

1. `AsyncContainer` and `SyncContainer` classes removed (use `Container` instead)
2. `Singleton`, `Resource`, `Dict`, and `List` provider types removed
3. All provider constructors now use keyword-only arguments
4. Provider resolution methods simplified (no `sync_` prefix)
5. Integration packages updated with new APIs
6. Provider casting mechanism changed (`.cast` attribute removed)
