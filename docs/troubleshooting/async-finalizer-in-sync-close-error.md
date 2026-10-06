# AsyncFinalizerInSyncCloseError

## Symptom

Arrives inside a `FinalizerError` (as one entry in its `.exceptions`), naming the type whose cached
instance has an async finalizer. `.instance_type` holds that type. A traceback shows it below the `FinalizerError`, and
`except* AsyncFinalizerInSyncCloseError` catches it.

## Cause

`close_sync()` cannot `await` anything. When it reaches a cached resource whose `CacheSettings`
finalizer is an async function, it can't run it synchronously, so it records this error for that entry
instead. Unlike a normal finalizer failure, it keeps the resource's cache entry intact rather than
discarding it.

## Fix

Use `close_async()` (or `async with container:`) for containers that hold any resource with an async
finalizer, since it's the only path that can actually run that cleanup:

```python
container.resolve(AsyncResource)   # has an async finalizer

try:
    container.close_sync()
except* exceptions.AsyncFinalizerInSyncCloseError:
    # cache retained, not lost
    ...

await container.close_async()      # recovers: runs the async finalizer, completes cleanup
```

Prefer `async with container:` (or `await close_async()`) by default whenever any provider might have
an async finalizer, and treat `close_sync()` as a fallback only for containers you know are entirely
sync.

## See also

- [Lifecycle: close-failure semantics](../providers/lifecycle.md#close-failure-semantics).
