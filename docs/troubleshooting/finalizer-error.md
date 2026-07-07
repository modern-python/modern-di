# FinalizerError

**Symptom**

Raised by `close_sync()` / `close_async()`, embedding the list of finalizer exceptions that occurred
during cleanup and whether the close was sync or async.

**Cause**

One or more cached providers' finalizers raised while the container was closing. Closing never stops
at the first failure — every finalizer runs regardless — so this error aggregates all of them rather
than surfacing just one.

**Fix**

Inspect `.finalizer_errors` for the individual exceptions and fix the offending finalizer(s):

```python
try:
    container.close_sync()
except exceptions.FinalizerError as exc:
    for err in exc.finalizer_errors:
        print(type(err).__name__, err)
```

Because every finalizer still ran, a broken one doesn't leak a resource a later finalizer would have
closed — only the exceptions themselves need attention, not the cleanup order. `.is_async` tells you
whether `close_sync()` or `close_async()` produced the error.

**Escape hatches**

If one entry in `.finalizer_errors` is an `AsyncFinalizerInSyncCloseError`, that specific resource's
cache was retained (not lost) — calling `await container.close_async()` afterward finalizes it and
completes cleanup.

## See also

- [Lifecycle: close-failure semantics](../providers/lifecycle.md#close-failure-semantics).
