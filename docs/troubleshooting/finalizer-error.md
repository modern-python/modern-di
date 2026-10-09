# FinalizerError

## Symptom

Raised by `close_sync()` / `close_async()` when finalizers fail during cleanup. The message is one
line naming each kind of error with its count:

```
FinalizerError: Container.close_sync() found 2 finalizer error(s): ConnectionError (1), ValueError (1)
```

It is an `ExceptionGroup`, so a traceback shows each finalizer exception below it, with a note naming
the type of the cached instance whose finalizer raised it, such as
`raised by the finalizer of a cached Database`.

## Cause

One or more cached providers' finalizers raised while the container was closing. Closing never stops
at the first failure: every finalizer runs regardless, so this error aggregates every failure.

## Fix

Inspect `.exceptions` for the individual exceptions and fix the offending finalizer(s):

```python
try:
    container.close_sync()
except exceptions.FinalizerError as exc:
    for err in exc.exceptions:
        print(type(err).__name__, err)
```

To handle one kind of finalizer failure and let the rest propagate, use `except*`:

```python
try:
    container.close_sync()
except* ConnectionError as group:
    for err in group.exceptions:
        print("cleanup failed:", err)
```

Because every finalizer still ran, a broken one doesn't leak a resource a later finalizer would have
closed. Only the exceptions themselves need attention, not the cleanup order. `.is_async` tells you
whether `close_sync()` or `close_async()` produced the error.

## Escape hatches

If one entry in `.exceptions` is an `AsyncFinalizerInSyncCloseError`, that specific resource's
cache was retained, and calling `await container.close_async()` afterward finalizes it
and completes cleanup.

## See also

- [Lifecycle: close-failure semantics](../providers/lifecycle.md#close-failure-semantics).
