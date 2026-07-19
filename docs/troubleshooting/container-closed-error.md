# ContainerClosedError

**Symptom**

Raised when resolving from, or building a child of, a container after it was closed.

**Cause**

`container.close_sync()` / `close_async()` (or exiting a `with container:` block) marks the container
closed. Any further `resolve()`, `resolve_provider()`, or `build_child_container()` call on that
container raises this error — there is no self-heal.

**Fix**

Re-enter the container before reusing it:

```python
with container:
    container.resolve(Settings)
# closed here

with container:                 # reopened cleanly
    container.resolve(Settings)
```

Or call `container.open()` explicitly if a context manager doesn't fit your flow. Build a fresh
container per unit of work (e.g. one per request) instead of trying to reuse a closed one across
units of work.

## See also

- [Migration: closed containers raise instead of self-healing](../migration/to-3.x.md#1-closed-containers-raise-instead-of-self-healing).
- [Lifecycle: closing and reopening](../providers/lifecycle.md#closing-and-reopening).
