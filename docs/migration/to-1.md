# Migration Guide: Upgrading to modern-di 1.x

This document describes the changes required to migrate from modern-di 0.x versions to modern-di 1.x.

## Overview

The migration to modern-di 1.x involves several key changes in the API, including:
- Updated import paths and class names
- Changes in container initialization and usage
- Modified provider resolution methods

## Key Changes

### 1. Import Path Changes

The following import paths and class names have changed:

- `BaseGraph` → `Group`
- `Container` → `AsyncContainer` or `SyncContainer` (depending on your needs)

For example:
```python
# Before (0.x)
from modern_di import BaseGraph, Container

# After (1.x)
from modern_di import Group, AsyncContainer, SyncContainer
```

### 2. Provider Changes

Several provider types were added, removed, or changed:

#### New Providers

- **ContextProvider**: A new provider type that allows injecting context values into dependencies. This is particularly useful for injecting framework-specific objects like requests, websockets, etc.

#### Removed Providers

- **Selector**: The `Selector` provider has been removed. Its functionality can be replicated using `Factory` providers combined with `ContextProvider`.
- **ContextAdapter**: The `ContextAdapter` provider has been removed and replaced with `ContextProvider`. Its functionality can also be replicated using `Factory` providers combined with `ContextProvider`.

#### Using ContextProvider with Factory as a Replacement

The combination of `ContextProvider` and `Factory` can replicate the functionality of both the old `Selector` and `ContextAdapter` providers:

```python
# Before (0.x) - Using Selector
def fetch_db_mode() -> str:
    # Some logic to determine which database to use
    return "write" if some_condition else "read"

dynamic_engine = providers.Selector(
    Scope.REQUEST,
    fetch_db_mode,
    write=database_engine,
    read=database_replica_engine,
)


# After (1.x) - Using ContextProvider with Factory for Selector replacement
# First, define a ContextProvider for any context you need
some_context = providers.ContextProvider(Scope.REQUEST, SomeContextType)

# Then use a Factory that takes the context and makes decisions
dynamic_engine = providers.Factory(
    Scope.REQUEST,
    choose_database_engine,  # A function that decides which engine to use
    context=some_context.cast,  # Pass the context to the factory function
    database_engine=database_engine.cast,
    database_replica_engine=database_replica_engine.cast,
)

# The factory function would look like:
def choose_database_engine(
    context: SomeContextType,
    database_engine: DatabaseEngine,
    database_replica_engine: DatabaseReplicaEngine,
) -> DatabaseEngine:
    # Replicate the selector logic here
    return database_engine if should_use_write_db(context) else database_replica_engine

```

### 3. Container Initialization

The single `Container` class has been split into two separate classes: `AsyncContainer` and `SyncContainer`.
However, it's important to note that `AsyncContainer` can still be used to synchronously resolve providers.

**Before (0.x):**
```python
# Synchronous container
container = Container()
container.sync_enter()

# Asynchronous container
container = Container()
container.async_enter()
```

**After (1.x):**
```python
# Synchronous container
sync_container = SyncContainer(groups=ALL_GROUPS)
sync_container.enter()

# Asynchronous container (can still resolve providers synchronously)
async_container = AsyncContainer(groups=ALL_GROUPS)
async_container.enter()

# Synchronously resolve a provider with AsyncContainer
instance = async_container.sync_resolve_provider(provider)

# Asynchronously resolve a provider with AsyncContainer
instance = await async_container.resolve_provider(provider)
```

The key difference is that `AsyncContainer` supports both synchronous and asynchronous provider resolution, while `SyncContainer` only supports synchronous resolution.
Choose `AsyncContainer` if you need to resolve both synchronous and asynchronous providers, or `SyncContainer` if you only need synchronous resolution.

### 4. Provider Resolution

The method for resolving providers has changed significantly. The dependency resolution pattern has been inverted - instead of calling resolution methods on the provider, you now call them on the container. This provides a more consistent and intuitive API.

**Before (0.x):**
```python
# Resolving a provider directly - called on the provider
instance = provider.sync_resolve(container)
instance = await provider.async_resolve(container)

# Resolving creators from a graph - called on the provider
await ioc.UseCases.create_chat_use_case.async_resolve(container)
```

**After (1.x):**
```python
# Resolving a provider directly - called on the container
instance = container.sync_resolve_provider(provider)
instance = await container.resolve_provider(provider)

# Resolving by type - called on the container
instance = container.sync_resolve(SomeType)
instance = await container.resolve(SomeType)
```

The key changes are:
1. **Inverted dependency**: Resolution is now called on the container instead of the provider
2. **Type-based resolution**: You can now resolve dependencies directly by type, not just by provider reference
3. **Consistent naming**: `sync_resolve_provider()` and `resolve_provider()` for provider-based resolution, `sync_resolve()` and `resolve()` for type-based resolution

### 5. Resolution by Dependency Type

One of the key new features in modern-di 1.x is the ability to resolve dependencies by type rather than by provider reference. This provides a more intuitive and flexible way to access dependencies.

To enable this feature, you must pass the `groups` parameter when initializing your container:

```python
# Initialize container with groups to enable type-based resolution
container = AsyncContainer(groups=ALL_GROUPS)
container.enter()

# Now you can resolve dependencies by type
instance = container.sync_resolve(SomeType)
instance = await container.resolve(SomeType)

# You can still resolve by provider reference if needed
instance = container.sync_resolve_provider(some_provider)
instance = await container.resolve_provider(some_provider)
```

The `groups` parameter is a list of `Group` classes that contain your providers. Each provider in these groups is registered with its return type, allowing the container to look up providers by type:

```python
from modern_di import Group, Scope, providers

class DatabaseGroup(Group):
    database_engine = providers.Singleton(Scope.APP, DatabaseEngine)
    repository = providers.Factory(Scope.REQUEST, Repository, db_engine=database_engine.cast)

# Register the group when creating the container
ALL_GROUPS = [DatabaseGroup]
container = AsyncContainer(groups=ALL_GROUPS)

# Now you can resolve by type
db_engine = container.sync_resolve(DatabaseEngine)
repository = await container.resolve(Repository)
```

This feature simplifies dependency access and makes the API more intuitive, as you no longer need to maintain references to specific providers throughout your codebase.

## Migration Steps

1**Update Import Statements**: Replace old import paths with new ones (`BaseGraph` → `Group`, `Container` → `AsyncContainer`/`SyncContainer`)
2**Update Provider Definitions**: Replace `Selector` and `ContextAdapter` providers with `Factory` and `ContextProvider` combinations where needed
3**Update Container Initialization**: Use `AsyncContainer(groups=ALL_GROUPS)` or `SyncContainer(groups=ALL_GROUPS)` instead of `Container()` (note that `AsyncContainer` supports both synchronous and asynchronous provider resolution)
4**Update Container Methods**: Replace `async_enter()` with `enter()` and `sync_resolve()` with `sync_resolve_provider()`
5**Update Provider Resolution**: Replace `provider.resolve(container)` with `container.resolve_provider(provider)` or `container.resolve(Type)` (resolution is now called on the container, not the provider)

## Breaking Changes

1. `BaseGraph` class renamed to `Group`
2. `Container` class replaced with `AsyncContainer` and `SyncContainer`
3. `async_enter()` method replaced with `enter()`
4. `sync_resolve()` method on providers replaced with `sync_resolve_provider()` on containers
5. `async_resolve()` method on providers replaced with `resolve_provider()` on containers
6. `Selector` provider type removed (use `Factory` with `ContextProvider` instead)
7. `ContextAdapter` provider type removed (use `ContextProvider` instead)
8. Manual provider overrides are handled differently
9. The way dependencies are declared in web framework applications has changed
10. Container initialization now requires passing groups explicitly
11. Dependency resolution is now called on containers instead of providers
