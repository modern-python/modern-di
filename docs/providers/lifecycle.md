# Lifecycle

How instances are created, cached, and cleaned up.

The code blocks below assume the following import, and `Dependencies` is a user-defined `Group`:

```python
from modern_di import Container, Scope, providers, exceptions
```

## Lazy initialization

`modern-di` creates instances on first resolve. There is no `init_resources()` or "eager startup" call: if a provider is never resolved, its creator never runs.

If you want a provider warmed up at startup (e.g. eager-connect the database engine), call `container.resolve(SomeType)` for it in your application's startup hook.

```python
container = Container(groups=[Dependencies])

# Warm caches at startup
container.resolve(AsyncEngine)
container.resolve(Settings)
```

## Caching and finalizers

`CacheSettings` controls two things: whether resolved instances are cached, and what to do when they're cleaned up.

```python
session = providers.Factory(
    create_session,
    scope=Scope.REQUEST,
    cache=providers.CacheSettings(finalizer=close_session),
)
```

- With `cache=True`, the provider returns the same instance for every resolve inside that scope's container. That is the singleton idiom; see [Cached factories](factories.md#cached-factories). Without `cache`, the provider creates a fresh instance every call.
- A finalizer is a callable that runs on the cached instance when the container is closed. It can be sync or async; `CacheSettings` auto-detects via `inspect.iscoroutinefunction()`. The finalizer takes one argument: the cached instance.

```python
def close_engine_sync(engine: Engine) -> None:
    engine.dispose()


async def close_engine_async(engine: AsyncEngine) -> None:
    await engine.dispose()
```

Both work; pick whichever matches the resource.

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

Closing a container runs its finalizers in reverse-creation order (creation order equals first-resolve order, since creation is lazy), then clears the cache.

## Close-failure semantics

Closing keeps going when a finalizer fails: one that raises does not abort the others. Every
finalizer runs; the exceptions are collected and re-raised together as a single `FinalizerError`
once cleanup finishes. `FinalizerError` is an `ExceptionGroup`: `.exceptions` holds the underlying
exceptions as a tuple, and `.is_async` records whether `close_sync()` or `close_async()` raised it.
So a broken finalizer can't leak a resource that a later finalizer would have closed.

Because it is an exception group, `except*` catches the finalizer errors by type. `except
FinalizerError` and `except ModernDIError` still catch the whole group:

```python
try:
    container.close_sync()
except* ConnectionError as group:
    # group is a FinalizerError holding only the ConnectionErrors; .is_async is kept
    for err in group.exceptions:
        print("cleanup failed:", err)
```

A finalizer that raises still clears its cache entry. The instance is dropped, and the next resolve
after reopening builds a fresh one. With `clear_cache=False` the entry is kept, as it is after a
finalizer that succeeds.

If `close_async()` is cancelled, or a finalizer raises a `BaseException` that is not an `Exception`
(such as `asyncio.CancelledError` or `KeyboardInterrupt`), that exception propagates at once. The
container is marked closed, and every resource whose finalizer has not completed, including the one
that was interrupted, stays queued. Awaiting `close_async()` again runs the remaining finalizers:

```python
try:
    await asyncio.wait_for(container.close_async(), timeout=5)
except TimeoutError:
    ...

await container.close_async()  # finalizes what the cancelled close did not reach
```

Calling `close_sync()` on a cached resource with an async finalizer is recoverable. `close_sync()`
cannot await, so when it reaches such a resource it produces an `AsyncFinalizerInSyncCloseError`,
delivered inside the aggregated `FinalizerError` (as an entry in `.exceptions`), since sync close
aggregates like any other failure. The resource's cache entry is **retained**
rather than discarded, so the resource is not lost: a later `await container.close_async()` finalizes
it correctly and completes the cleanup.

```python
# Resource with an async finalizer, resolved into the cache.
container.resolve(AsyncResource)

try:
    container.close_sync()
except* exceptions.AsyncFinalizerInSyncCloseError:
    # the cache was kept, nothing was finalized yet.
    ...

await container.close_async()  # recovers — runs the async finalizer now
```

Prefer `async with container:` (or `await close_async()`) whenever any provider has an async
finalizer; the sync path is only a safety net.

## Closing and reopening

A constructed container is **open from construction**: `container.closed` is `False` the moment
`Container(...)` returns, with no `open()` step required before the first `resolve()` / `resolve_provider()` call.
`build_child_container()` never checks or touches any container's open/closed state (it only reads
the parent's shared registries and scope map), and the returned child starts open too, same as any
fresh container. `close_sync()` / `close_async()` run the finalizers (in reverse-creation order, as
above) and mark the container closed; entering `with container:` (or `async with`) is the idiomatic
way to guarantee that close runs, even on an exception.

The container counts as closed as soon as `close_sync()` or `close_async()` starts, so a finalizer
that resolves from its own container gets `ContainerClosedError`. Pass a finalizer what it needs
through the cached instance instead of resolving it during close.

Resolving from a closed container, directly or through a child whose resolve reaches back into
that container's scope, raises `ContainerClosedError`, and the creator does not run. The container
stays closed until it is reopened. Building a child of a closed container still works, and the child
resolves what it owns; only a provider that resolves in the closed scope raises. Calling `open()`
reopens the container, and so does entering `with container:` or `async with container:` again,
because `__enter__` and `__aenter__` call `open()`:

```python
container = Container(groups=[Dependencies])

with container:
    container.resolve(Settings)
# closed here: finalizers ran

container.resolve(Settings)  # raises ContainerClosedError

with container:                 # reopened by __enter__
    container.resolve(Settings)
```

See [Troubleshooting: ContainerClosedError](../troubleshooting/container-closed-error.md) for what to
check when a container is closed where you did not expect it, and
[Migration: To 4.x](../migration/to-4.x.md#resolving-on-a-closed-container-raises) for the 3.x
behavior, which warned and reopened instead.

How a cached instance survives this cycle depends on its `CacheSettings`:

- With the default `clear_cache=True`, the instance is finalized at close and rebuilt on
  the next resolve after reopen.
- With `clear_cache=False`, the cached instance survives close→reopen and is returned
  again, the *same object* (its finalizer runs once, at the first close, and is not
  re-run on later closes). Use this for a shared resource whose identity must stay stable
  across restarts.
- Overrides are configuration, separate from cached instances. Closing a container does
  not touch them, so an override set before close→reopen still applies after it. Clear
  one with `reset_override()` or by exiting the `with container.override(...)` block.

!!! caution "The context manager is not reference-counted"
    Nesting `with container:` on the **same** object closes it on the inner `with` exit,
    not the outer one. Use one `with` block per container, or build a child container for
    the inner scope.

## Per-scope finalization

Each container has its own finalizers, the ones for the providers it cached. When a child container exits its `with` block, only the child's finalizers run; the parent's stay alive for as long as the parent does.

```python
app_container = Container(groups=[Dependencies])
app_container.validate()  # optional: fails fast here instead of at whichever resolve hits a problem first

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

`container.validate()` is the only thing that walks the graph. Nothing validates automatically:
not construction, not `open()`, not `add_providers`, not `resolve()`. A container is fully usable,
and stays usable, without ever calling `validate()`; a broken graph nobody validates surfaces
at whichever resolve first hits the problem, as an ordinary resolution error.

Call it explicitly, whenever you want the whole graph checked at once: cycles, inverted scope
dependencies, and missing required dependencies, all in a single pass:

```python
container = Container(groups=[Dependencies])
container.validate()  # walks now; raises ValidationFailedError if any issue is found
```

It aggregates every issue it finds into one `exceptions.ValidationFailedError` rather than stopping
at the first; see [Troubleshooting: ValidationFailedError](../troubleshooting/validation-failed-error.md).
Call it right after building the container for a construction-time check, or later. A framework
integration that registers its own providers after construction (via `add_providers`) should call it
after that registration, so the complete graph is what gets checked; see [Writing an
integration](../integrations/writing-integrations.md#lifecycle-rules).

A repeat `validate()` after a clean walk is free: it memoizes against the registry's contents and
only re-walks once something has changed it (`register`/`add_providers`). Validation has no
runtime cost after that. Turn it on in a startup path or a single test, where it catches the bugs
you don't want to discover under load.

## See also

- [Scopes](scopes.md): child containers and per-scope finalization.
- [Factories](factories.md): `CacheSettings` is configured on the factory itself.
- [Async resources via lifespan](../recipes/async-lifespan.md): sync creator + async finalizer is the most common shape.
