# FinalizerError

## Symptom

Raised by `close_sync()` / `close_async()` when finalizers fail during cleanup. The message's first
line names each kind of error with its count:

```text
modern_di.exceptions.lifecycle.FinalizerError: Container.close_sync() found 2 finalizer error(s): ConnectionError (1), ValueError (1)
See: https://modern-di.modern-python.org/troubleshooting/finalizer-error/
```

It is an `ExceptionGroup`, so a traceback shows each finalizer exception below it, with a note naming
the type of the cached instance whose finalizer raised it, such as
`raised by the finalizer of a cached Database`. `.is_async` tells you whether `close_sync()` or
`close_async()` raised it.

## Cause

One or more finalizers of cached providers raised while the container was closing. Finalizers run
newest first, in the reverse of the order their instances were created, and closing never stops at
the first failure. Every finalizer runs, and this error collects every failure.

## Fix

Inspect `.exceptions` for the individual exceptions and fix the finalizers that raised:

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, exceptions, providers


class Database: ...


class Cache: ...


def close_database(database: Database) -> None:
    raise ConnectionError("database is gone")


def close_cache(cache: Cache) -> None:
    raise ValueError("cache is gone")


class Dependencies(Group):
    database = providers.Factory(Database, scope=Scope.APP, cache=providers.CacheSettings(finalizer=close_database))
    cache = providers.Factory(Cache, scope=Scope.APP, cache=providers.CacheSettings(finalizer=close_cache))


container = Container(groups=[Dependencies])
container.resolve(Database)
container.resolve(Cache)
-->

```python
try:
    container.close_sync()
except exceptions.FinalizerError as exc:
    for err in exc.exceptions:
        print(type(err).__name__, err)
```

To handle one kind of finalizer failure and let the rest propagate, use `except*`:

<!-- invisible-code-block: python
container.open()
container.resolve(Database)
-->

```python
try:
    container.close_sync()
except* ConnectionError as group:
    for err in group.exceptions:
        print("cleanup failed:", err)
```

What `except*` does not catch is raised again as a `FinalizerError` holding only the remaining
errors.

A finalizer that raised is not retried. Its instance is dropped from the cache, so a later close does
not call that finalizer again, and resolving after a reopen builds a new instance. With
`clear_cache=False` the instance stays cached and a reopen returns it, but its finalizer still does
not run again. Because every other finalizer still ran, a broken one does not leak a resource that a
later finalizer would have closed.

An `AsyncFinalizerInSyncCloseError` entry is the exception to this: `close_sync()` keeps that
instance cached, and a later `await container.close_async()` runs its finalizer. See
[AsyncFinalizerInSyncCloseError](async-finalizer-in-sync-close-error.md).

## See also

- [Lifecycle: close-failure semantics](../providers/lifecycle.md#close-failure-semantics) — what
  closing does when a finalizer fails or is cancelled.
- [AsyncFinalizerInSyncCloseError](async-finalizer-in-sync-close-error.md) — an async finalizer
  reached by `close_sync()`.
