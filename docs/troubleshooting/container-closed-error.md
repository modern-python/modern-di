# ContainerClosedError

## Symptom

Raised from `resolve()` or `resolve_provider()` (and so from `resolve_dependency()` and every
integration's `FromDI`) when the call reaches a container that was closed:

```text
Container (scope APP) is closed. Reopen it with `open()` or by re-entering `with`/`async with` before resolving from it or from any of its child containers.
```

`.container_scope` names the closed container. When a child's resolve reaches back into a closed
ancestor's scope, as when an APP-scoped provider is resolved through an open REQUEST child, it names
the ancestor, not the child you called.

## Cause

`close_sync()`, `close_async()`, and leaving a `with` / `async with` block run the container's
finalizers and mark it closed. Nothing reopens it on its own: every resolve that lands on it raises
until the container is reopened, and the creator never runs. A child container built before or
after the close does not reopen its parent either. Building a child of a closed container still
works, and so does resolving anything the child owns, but any provider that resolves in the closed
ancestor's scope raises.

A fresh container is open from construction, so this never means "you forgot to open it".

## Fix

Two cases, and they want different fixes:

- **The reuse is deliberate.** A test harness that enters the same container twice, a broker that
  stops and starts, or a framework lifespan that runs more than once in one process all close and
  then restart the same object. Reopen it explicitly before the next use: call `container.open()`,
  or re-enter it with `with` / `async with`, which calls `open()` for you. Integrations do this in
  their startup hook.

  ```python
  container = Container(groups=[Dependencies])

  with container:
      container.resolve(Settings)
  # closed here: finalizers ran

  container.resolve(Settings)  # Broken: raises ContainerClosedError

  with container:  # Works: __enter__ reopens it
      container.resolve(Settings)
  ```

- **The reuse is not deliberate.** Something holds a reference to the container past its lifetime,
  such as a request handler that kept the container from an earlier unit of work, or a background
  task still running after the application shut down. Find where that reference comes from and stop
  it outliving the container. Reopening here would hide the leak, and anything it cached would miss
  its finalizer at the real shutdown.

## See also

- [Lifecycle: closing and reopening](../providers/lifecycle.md#closing-and-reopening) — what close
  runs and what survives a reopen.
- [Migration: To 4.x](../migration/to-4.x.md#resolving-on-a-closed-container-raises) — the 3.x
  warn-and-reopen behavior this replaced.
