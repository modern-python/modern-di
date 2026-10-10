# AsyncFinalizerInSyncCloseError

## Symptom

`close_sync()` raises a [`FinalizerError`](finalizer-error.md), and one of its `.exceptions` is an
`AsyncFinalizerInSyncCloseError`:

```text
  + Exception Group Traceback (most recent call last):
  |   ...
  | modern_di.exceptions.lifecycle.FinalizerError: Container.close_sync() found 1 finalizer error(s): AsyncFinalizerInSyncCloseError (1)
  | See: https://modern-di.modern-python.org/troubleshooting/finalizer-error/
  +-+---------------- 1 ----------------
    | modern_di.exceptions.lifecycle.AsyncFinalizerInSyncCloseError: Cannot run async finalizer for AsyncResource during sync close. Use `await container.close_async()` (or `async with container:`) instead.
    | See: https://modern-di.modern-python.org/troubleshooting/async-finalizer-in-sync-close-error/
    +------------------------------------
```

`.instance_type` holds the type of the cached instance, and `except* AsyncFinalizerInSyncCloseError`
catches it.

## Cause

`close_sync()` cannot `await`. It records this error for a cached instance whose finalizer is an
`async def`, and for one whose sync finalizer returns an awaitable. In both cases it keeps the
instance cached, unlike a finalizer that raised, whose instance is dropped. While the instance stays
cached, a repeated `close_sync()` reports it again, and resolving after a reopen returns the same
instance.

## Fix

Close the container with `close_async()` or `async with container:`, the only paths that can run an
async finalizer. After a `close_sync()` that reported this error, `await container.close_async()`
runs the finalizer and finishes the cleanup:

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, exceptions, providers


class AsyncResource:
    async def close(self) -> None: ...


async def close_resource(resource: AsyncResource) -> None:
    await resource.close()


class Dependencies(Group):
    resource = providers.Factory(
        AsyncResource, scope=Scope.APP, cache=providers.CacheSettings(finalizer=close_resource)
    )


container = Container(groups=[Dependencies])
-->

```python
container.resolve(AsyncResource)

try:
    container.close_sync()
except* exceptions.AsyncFinalizerInSyncCloseError:
    pass  # AsyncResource is still cached

await container.close_async()  # runs close_resource
```

Use `close_sync()` only for containers you know hold no async finalizer.

## See also

- [Lifecycle: async finalizers and `close_sync()`](../providers/lifecycle.md#async-finalizers-and-close_sync)
  — how `close_sync()` treats an async finalizer.
- [FinalizerError](finalizer-error.md) — the group this error arrives in.
