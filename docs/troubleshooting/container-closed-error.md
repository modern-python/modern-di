# ContainerClosedError

**Symptom**

Raised when resolving from, or building a child of, a container after it was closed.

**Cause**

`container.close_sync()` / `close_async()` (or exiting a `with container:` block) marks the container
closed. In modern-di **3.0**, any further `resolve()`, `resolve_provider()`, or
`build_child_container()` call on that container raises this error instead of quietly working.

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

**Escape hatches**

Today (2.x), this reuse doesn't raise yet — it emits `ContainerClosedWarning` and self-reopens the
container so the call still succeeds. Escalate that warning to an error now to catch the pattern
before upgrading, using the readiness recipe on the migration page below.

## See also

- [Migration: closed containers raise instead of self-healing](../migration/to-3.x.md#1-closed-containers-raise-instead-of-self-healing).
- [Lifecycle: closing and reopening](../providers/lifecycle.md#closing-and-reopening).
