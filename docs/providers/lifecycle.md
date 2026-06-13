# Lifecycle

How instances are created, cached, and cleaned up.

## Lazy initialization

`modern-di` creates instances on first resolve. There is no `init_resources()` or "eager startup" call — if a provider is never resolved, its creator never runs.

If you want a provider warmed up at startup (e.g. eager-connect the database engine), call `container.resolve(SomeType)` for it in your application's startup hook. Framework integrations are a good place for this.

```python
container = Container(groups=[Dependencies], validate=True)

# Warm caches at startup
container.resolve(AsyncEngine)
container.resolve(Settings)
```

## Caching and finalizers

`CacheSettings` controls two things: whether resolved instances are cached, and what to do when they're cleaned up.

```python
session = providers.Factory(
    scope=Scope.REQUEST,
    creator=create_session,
    cache_settings=providers.CacheSettings(finalizer=close_session),
)
```

- **Caching.** With `cache_settings=CacheSettings()`, the provider returns the same instance for every resolve inside that scope's container. Without `cache_settings`, the provider creates a fresh instance every call.
- **Finalizer.** A callable that runs on the cached instance when the container is closed. Sync or async — `CacheSettings` auto-detects via `inspect.iscoroutinefunction()`. The finalizer takes one argument: the cached instance.

```python
def close_engine_sync(engine: Engine) -> None:
    engine.dispose()


async def close_engine_async(engine: AsyncEngine) -> None:
    await engine.dispose()
```

Both work — pick whichever matches the resource.

## Closing the container

Three ways to run finalizers:

```python
# Sync
container.close_sync()

# Async
await container.close_async()

# Context manager (preferred — cleanup runs even on exceptions)
with container:
    ...

async with container:
    ...
```

Closing a container runs its finalizers in reverse-resolve order, then clears the cache.

## Closing and reopening

Entering `with container:` (or `async with`) opens the container; exiting calls
`close_sync()` / `close_async()`, which run the finalizers (in reverse-creation order, as
above) and mark the container closed.

While a container is closed, resolving a dependency — or building a child container —
raises `ContainerClosedError`. Re-entering `with container:` reopens it, and resolution
works again:

```python
container = Container(groups=[Dependencies])

with container:
    container.resolve(Settings)
# closed here — finalizers ran

# container.resolve(Settings)  -> raises ContainerClosedError

with container:                 # reopened
    container.resolve(Settings)
```

How a cached instance survives this cycle depends on its `CacheSettings`:

- With the default `clear_cache=True`, the instance is finalized at close and rebuilt on
  the next resolve after reopen.
- With `clear_cache=False`, the cached instance survives close→reopen and is returned
  again — the *same object* (its finalizer runs once, at the first close, and is not
  re-run on later closes). Use this for a shared resource whose identity must stay stable
  across restarts.

!!! caution "The context manager is not reference-counted"
    Nesting `with container:` on the **same** object closes it on the inner `with` exit,
    not the outer one. Use one `with` block per container, or build a child container for
    the inner scope.

## Per-scope finalization

Each container has its own finalizers — the ones for the providers it cached. When a child container exits its `with` block, only the child's finalizers run; the parent's stay alive for as long as the parent does.

```python
app_container = Container(groups=[Dependencies], validate=True)

async with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
    session = request_container.resolve(AsyncSession)
    # work...
# request_container's REQUEST-scope finalizers ran (e.g. session.close())
# app_container's APP-scope finalizers DID NOT run

await app_container.close_async()
# now app_container's finalizers run (e.g. engine.dispose())
```

Framework integrations handle this automatically: they build the REQUEST child container per request and exit its context at the end of the request, then call `close_async()` on the APP container at app shutdown.

## Validation

`Container(groups=[...], validate=True)` runs the following checks at startup:

- **Cycle detection.** Provider A depending on B depending on A raises `CircularDependencyError`.
- **Scope chain check.** A provider that depends on a shorter-lived provider raises an error (see [Scopes](scopes.md)).
- **Missing providers.** A creator parameter typed `Foo` with no registered `Foo` provider raises an error.

Validation has no runtime cost after startup. Turn it on — it catches the bugs you don't want to discover under load.

You can also call `container.validate()` manually after the container is built (useful in tests).

## See also

- [Scopes](scopes.md) — child containers and per-scope finalization.
- [Factories](factories.md) — `CacheSettings` is configured on the factory itself.
- [Async resources via lifespan](../recipes/async-lifespan.md) — sync creator + async finalizer is the most common shape.
