# Migration Guide: Upgrading to modern-di 2.x

modern-di 2.x merges the container classes, moves providers to keyword-only arguments, removes four provider types in favor of `Factory`, and drops async resolution. Breaking changes, once:

1. **`AsyncContainer`/`SyncContainer` → `Container`** (single class, both sync and async operations):

    ```python
    # Before (1.x)
    from modern_di import AsyncContainer, SyncContainer
    async_container = AsyncContainer(groups=ALL_GROUPS)
    async_container.enter()

    # After (2.x)
    from modern_di import Container
    container = Container(groups=ALL_GROUPS, validate=True)  # no explicit enter() needed
    container.close_sync()       # or: await container.close_async()
    ```

    `with`/`async with container.build_child_container(...)` still works for automatic cleanup; `close_sync()`/`close_async()` are also available for manual lifecycle control. The framework integration packages were updated with matching new APIs.

2. **All provider constructors are keyword-only.**

    ```python
    # Before (1.x)
    factory = providers.Factory(Scope.REQUEST, MyClass, arg1="value1")

    # After (2.x)
    factory = providers.Factory(scope=Scope.REQUEST, creator=MyClass, kwargs={"arg1": "value1"})
    ```

3. **`Singleton`, `Resource`, `Dict`, `List` removed** — all four map onto `Factory`:

    ```python
    # Before (1.x)
    singleton = providers.Singleton(Scope.APP, create_singleton)
    resource = providers.Resource(Scope.REQUEST, create_resource)

    # After (2.x)
    singleton = providers.Factory(scope=Scope.APP, creator=create_singleton, cache=True)
    resource = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_resource,
        cache=providers.CacheSettings(finalizer=lambda r: r.close()),
    )
    ```

    `Dict`/`List` have no provider equivalent — write a plain creator function that returns the
    collection and wrap it in a `Factory`. `clear_cache` defaults to `True` (old `Resource`
    semantics: finalizer runs on close, instance rebuilt on next resolve); set `clear_cache=False`
    only when the same object must survive a close→reopen cycle.

4. **Resolution is sync-only** — no more `sync_` prefix, no `await` on resolution (async *finalizers* are still supported via `CacheSettings(finalizer=async_fn)` and `await container.close_async()`):

    ```python
    # Before (1.x)
    instance = await container.resolve_provider(provider)

    # After (2.x)
    instance = container.resolve_provider(provider)
    ```

5. **`.cast` removed** — wiring is by type instead:

    | 1.x | 2.x |
    |---|---|
    | `dep=other_provider.cast` (a provider dependency) | Drop the argument — annotate the creator parameter with the dependency's type. |
    | `value=settings.host` (a static value) | Pass it in `kwargs={"value": ...}`. |
    | a request/context value | Register a `ContextProvider` for that type (see [Context](../providers/context.md)). |

    ```python
    # 1.x
    service = providers.Factory(MyService, db_engine=database_engine.cast)

    # 2.x — MyService.__init__(self, db_engine: DBEngine); resolved by type
    service = providers.Factory(scope=Scope.APP, creator=MyService)
    ```
