# Migration Guide: Upgrading to modern-di 1.x

!!! warning "Historical guide"
    This guide covers migrating from 0.x to 1.x. The APIs shown here (`AsyncContainer`, `SyncContainer`, `providers.Singleton`, `.cast`) were **removed in 2.x**.
    If you are on 1.x today, also follow the [2.x migration guide](to-2.x.md) to reach the current API.

modern-di 1.x inverts where resolution methods live and replaces a handful of provider types. Breaking changes, once:

1. **`BaseGraph` → `Group`**; single `Container` → `AsyncContainer` or `SyncContainer` (async supports both sync and async resolution; sync is sync-only).

    ```python
    # Before (0.x)
    from modern_di import BaseGraph, Container

    # After (1.x)
    from modern_di import Group, AsyncContainer, SyncContainer

    sync_container = SyncContainer(groups=ALL_GROUPS)
    sync_container.enter()  # replaces Container().sync_enter()
    ```

2. **Resolution moved from provider to container**, and can now target a type directly (requires passing `groups=` at construction):

    ```python
    # Before (0.x)
    instance = provider.sync_resolve(container)
    instance = await provider.async_resolve(container)

    # After (1.x)
    instance = container.sync_resolve_provider(provider)
    instance = await container.resolve_provider(provider)
    instance = container.sync_resolve(SomeType)   # new: resolve by type
    instance = await container.resolve(SomeType)
    ```

    Manual provider overrides and the way dependencies are declared in web-framework applications changed accordingly — both now go through the container and integration APIs.

3. **`Selector` and `ContextAdapter` removed** — replace both with `Factory` + `ContextProvider`:

    ```python
    # Before (0.x)
    dynamic_engine = providers.Selector(Scope.REQUEST, fetch_db_mode, write=w, read=r)

    # After (1.x)
    mode = providers.ContextProvider(Scope.REQUEST, SomeContextType)
    dynamic_engine = providers.Factory(Scope.REQUEST, choose_engine, context=mode.cast, write=w.cast, read=r.cast)
    ```

4. **`AttrGetter` removed** — reference the provider directly, or write a small factory function that extracts the attribute.
5. **Factory attribute access removed** (`.async_provider`/`.sync_provider`) — inject the container itself and resolve dependencies manually instead of injecting a factory function.
6. **`async_enter()` → `enter()`.**

## More

See the [2.x migration guide](to-2.x.md) to move from here to the current API.
