# Lifecycle

`modern-di` creates an instance on first resolve, keeps a cached instance in the container at its
provider's scope, and runs its finalizer when that container closes, newest instance first.

The code blocks below assume the following import, and `Dependencies` is a user-defined `Group`:

```python
from modern_di import Container, Scope, providers, exceptions
```

## Lazy initialization

`modern-di` creates instances on first resolve. There is no `init_resources()` or "eager startup" call: if a provider is never resolved, its creator never runs.

If you want a provider warmed up at startup (e.g. eager-connect the database engine), call `container.resolve(SomeType)` for it in your application's startup hook.

<!-- invisible-code-block: python
from modern_di import Group


class Settings: ...


class Engine:
    def dispose(self) -> None: ...


class AsyncEngine:
    async def dispose(self) -> None: ...


class AsyncSession:
    async def close(self) -> None: ...


def create_session(engine: AsyncEngine) -> AsyncSession:
    return AsyncSession()


async def close_session(session: AsyncSession) -> None:
    await session.close()


class Dependencies(Group):
    settings = providers.Factory(Settings, cache=True)
    engine = providers.Factory(AsyncEngine, cache=providers.CacheSettings(finalizer=AsyncEngine.dispose))
    session = providers.Factory(
        create_session,
        scope=Scope.REQUEST,
        cache=providers.CacheSettings(finalizer=close_session),
    )
-->

```python
container = Container(groups=[Dependencies])

# Warm caches at startup
container.resolve(AsyncEngine)
container.resolve(Settings)
```

## Caching and finalizers

`cache=True` keeps one instance per container at the provider's scope; see
[Cached factories](factories.md#cached-factories) and
[Scope and caching](scopes.md#scope-and-caching). `CacheSettings` adds a finalizer, a callable that
receives the cached instance when its container closes:

```python
session = providers.Factory(
    create_session,
    scope=Scope.REQUEST,
    cache=providers.CacheSettings(finalizer=close_session),
)
```

A finalizer takes one argument, the instance, and its return value is ignored. Besides a function
like `close_session`, an unbound method works, because Python passes the instance as `self`:

```python
engine = providers.Factory(Engine, cache=providers.CacheSettings(finalizer=Engine.dispose))
async_engine = providers.Factory(AsyncEngine, cache=providers.CacheSettings(finalizer=AsyncEngine.dispose))
```

Finalizers can be sync or async. `CacheSettings` detects an async one with
`inspect.iscoroutinefunction()`, and `close_async()` also awaits whatever a sync callable returns,
so `lambda client: client.aclose()` works there. `close_sync()` cannot await either kind; see
[Async finalizers and `close_sync()`](#async-finalizers-and-close_sync).

Finalizers run newest first. A dependency is created before the instance that uses it, so the
session closes before the engine it was built from.

## Closing the container

Three ways to run finalizers:

<!-- invisible-code-block: python
container = Container(groups=[Dependencies])
-->

```python
# Sync
container.close_sync()

# Async
await container.close_async()

# Context manager (preferred: cleanup runs even on exceptions)
with container:
    ...

async with container:
    ...
```

Closing runs the container's finalizers newest first, then clears its cache.

### Per-scope finalization

Each container finalizes only the instances it cached. When a child container exits its `with`
block, the child's finalizers run and the parent's instances stay alive:

```python
app_container = Container(groups=[Dependencies])

async with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
    session = request_container.resolve(AsyncSession)
# the REQUEST container closed the session; the APP engine is still open

await app_container.close_async()
# now the engine is disposed
```

Framework integrations close each request's child container for you. Most also close the APP
container at shutdown with `close_async()`. Flask, gRPC and Typer leave the APP container to you,
and Celery closes it with `close_sync()`, so APP-scoped finalizers there must be sync. Each
[integration page](../integrations/fastapi.md) says which applies.

## Close-failure semantics

### Every finalizer runs

Closing keeps going when a finalizer raises, so one broken finalizer does not leak the resources
after it. The errors are raised together as one `FinalizerError` once every finalizer has run.
`FinalizerError` is an `ExceptionGroup`: `.exceptions` holds the errors, and `.is_async` records
whether `close_sync()` or `close_async()` raised it.

`except*` catches the finalizer errors by type, and `except FinalizerError` or
`except ModernDIError` catches the whole group:

<!-- invisible-code-block: python
class Connection: ...


def close_connection(connection: Connection) -> None:
    raise ConnectionError("connection reset")


class ConnectionDependencies(Group):
    connection = providers.Factory(Connection, cache=providers.CacheSettings(finalizer=close_connection))


container = Container(groups=[ConnectionDependencies])
container.resolve(Connection)
-->

```python
try:
    container.close_sync()
except* ConnectionError as group:
    # group is a FinalizerError holding only the ConnectionErrors; .is_async is kept
    for err in group.exceptions:
        print("cleanup failed:", err)
```

A finalizer that raises still drops its cached instance, and the next resolve after reopening
builds a fresh one. With `clear_cache=False` the instance is kept, as it is after a finalizer that
succeeds.

### Async finalizers and `close_sync()`

`close_sync()` cannot await. When it reaches an instance with an async finalizer, it adds an
`AsyncFinalizerInSyncCloseError` to the `FinalizerError` and keeps the instance cached, so a later
`await container.close_async()` still finalizes it:

<!-- invisible-code-block: python
class AsyncResource: ...


async def close_async_resource(resource: AsyncResource) -> None: ...


class AsyncResourceDependencies(Group):
    async_resource = providers.Factory(AsyncResource, cache=providers.CacheSettings(finalizer=close_async_resource))


container = Container(groups=[AsyncResourceDependencies])
-->

```python
container.resolve(AsyncResource)

try:
    container.close_sync()
except* exceptions.AsyncFinalizerInSyncCloseError:
    ...  # the instance is still cached, nothing was finalized

await container.close_async()  # runs the async finalizer
```

Use `async with container:` or `await container.close_async()` when any provider has an async
finalizer.

### Cancelled close

If `close_async()` is cancelled, or a finalizer raises a `BaseException` that is not an `Exception`
(such as `asyncio.CancelledError` or `KeyboardInterrupt`), that exception propagates at once. The
container is marked closed, and every instance whose finalizer has not completed, including the
interrupted one, stays queued. Awaiting `close_async()` again runs the remaining finalizers:

<!-- invisible-code-block: python
import asyncio
-->

```python
try:
    await asyncio.wait_for(container.close_async(), timeout=5)
except TimeoutError:
    ...

await container.close_async()  # finalizes what the cancelled close did not reach
```

## Closing and reopening

A new container is open, so it resolves right away with no `open()` call. A child from
`build_child_container()` starts open too.

The container counts as closed as soon as `close_sync()` or `close_async()` starts, so a finalizer
that resolves from its own container gets `ContainerClosedError`. Give a finalizer what it needs
through the cached instance.

After close, resolving raises `ContainerClosedError` and the creator does not run. That includes a
resolve through a child that reaches the closed container. A child of a closed container can still
be built and resolves what it owns. `open()` reopens the container, and so does entering
`with container:` or `async with container:` again:

<!-- raises: ContainerClosedError -->

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

What survives close and reopen depends on `CacheSettings`:

- With the default `clear_cache=True`, the instance is finalized at close and rebuilt on the next
  resolve after reopening.
- With `clear_cache=False`, reopening returns the same object, and its finalizer runs only at the
  first close. That object has already been through its finalizer, so use this only for a resource
  that still works afterwards.
- Overrides are configuration, not cached instances, so closing does not touch them. Clear one with
  `reset_override()` or by exiting the `with container.override(...)` block.

!!! caution "The context manager is not reference-counted"
    Nesting `with container:` on the **same** object closes it on the inner `with` exit,
    not the outer one. Use one `with` block per container, or build a child container for
    the inner scope.

## Validation

`container.validate()` checks the whole graph in one pass: cycles, dependencies on a deeper scope,
and dependencies nothing provides. Nothing else validates, not construction, `open()`,
`add_providers` or `resolve()`. Without it, a broken graph surfaces at the first resolve that
reaches the problem.

```python
container = Container(groups=[Dependencies])
container.validate()  # raises ValidationFailedError listing every issue
```

It reports every issue in one `exceptions.ValidationFailedError` instead of stopping at the first;
see [Troubleshooting: ValidationFailedError](../troubleshooting/validation-failed-error.md). An
integration that registers its own providers with `add_providers` should validate after that; see
[Writing an integration](../integrations/writing-integrations.md#lifecycle-rules).

A repeat `validate()` returns at once until `add_providers` changes the registry, and validation
adds nothing to resolve time. Call it at startup or in one test.

## See also

- [Scopes](scopes.md): child containers and which container caches an instance.
- [Factories](factories.md): `CacheSettings` is configured on the factory itself.
- [Async resources via lifespan](../recipes/async-lifespan.md): sync creator + async finalizer is the most common shape.
