# ContainerClosedError

**Symptom**

Raised when resolving from, or building a child of, a container that is **not open** — either one
never opened, or one closed after use. The message reads: `Container (scope APP) is not open — enter
it with with/async with or call open() ...`.

**Cause**

A container starts **unopened**: a freshly-constructed `Container(...)` must be entered before use.
Entering it (`with` / `async with` / `container.open()`) opens it; `container.close_sync()` /
`close_async()` (or exiting a `with container:` block) marks it closed again. While unopened or
closed, any `resolve()`, `resolve_provider()`, or `build_child_container()` call raises this error —
there is no self-heal.

**Fix**

Open the container before using it:

```python
with container:                 # opens on enter, closes on exit
    container.resolve(Settings)

with container:                 # reopened cleanly for the next unit of work
    container.resolve(Settings)
```

Or call `container.open()` explicitly if a context manager doesn't fit your flow (e.g. a framework
startup hook). Building a child requires the parent be open first, and the returned child must itself
be opened before use. Build a fresh child container per unit of work (e.g. one per request).

## See also

- [Migration: closed containers raise instead of self-healing](../migration/to-3.x.md#1-closed-containers-raise-instead-of-self-healing).
- [Lifecycle: closing and reopening](../providers/lifecycle.md#closing-and-reopening).
