# AsyncFinalizerInSyncCloseError

**Symptom**

Arrives wrapped inside a `FinalizerError` (as one entry in `.finalizer_errors`), naming the type whose
cached instance has an async finalizer.

**Cause**

`close_sync()` cannot `await` anything. When it reaches a cached resource whose `CacheSettings`
finalizer is an async function, it can't run it synchronously, so it records this error for that entry
instead — and, unlike a normal finalizer failure, keeps the resource's cache entry intact rather than
discarding it.

**Fix**

Use `close_async()` (or `async with container:`) for containers that hold any resource with an async
finalizer — it's the only path that can actually run that cleanup:

```python
container.resolve(AsyncResource)   # has an async finalizer

try:
    container.close_sync()
except exceptions.FinalizerError as exc:
    # exc.finalizer_errors contains an AsyncFinalizerInSyncCloseError — cache retained, not lost
    ...

await container.close_async()      # recovers: runs the async finalizer, completes cleanup
```

Prefer `async with container:` (or `await close_async()`) by default whenever any provider might have
an async finalizer, and treat `close_sync()` as a fallback only for containers you know are entirely
sync.

## See also

- [Lifecycle: close-failure semantics](../providers/lifecycle.md#close-failure-semantics).
