# ContainerClosedError

## Symptom

Raised from `resolve()` or `resolve_provider()` (and so from `resolve_dependency()` and every
integration's `FromDI`) when the call reaches a container that was closed:

```text
modern_di.exceptions.container.ContainerClosedError: Container (scope APP) is closed. Reopen it with `open()` or by re-entering `with`/`async with` before resolving from it or from any of its child containers.
See: https://modern-di.modern-python.org/troubleshooting/container-closed-error/
```

`.container_scope` names the closed container. When a child's resolve reaches back into a closed
ancestor's scope, as when an APP-scoped provider is resolved through an open REQUEST child, it names
the ancestor, not the child you called.

## Cause

`close_sync()`, `close_async()`, and leaving a `with` / `async with` block run the container's
finalizers and mark it closed. Every resolve that lands on a closed container raises, and the
creator never runs. A child container does not reopen its parent, whether it was built before or
after the close. Building a child of a closed container still works, and so does resolving anything
the child owns, but any provider that resolves in the closed ancestor's scope raises.

A fresh container is open from construction, so this never means "you forgot to open it".

## Fix

Reopen the container before resolving from it again. Call `container.open()`, or enter it again
with `with` / `async with`, whose `__enter__` and `__aenter__` call `open()` for you. Integrations
call `open()` in their startup hook.

<!-- invisible-code-block: python
from modern_di import Container, Group, providers


class Settings: ...


class Dependencies(Group):
    settings = providers.Factory(Settings)


container = Container(groups=[Dependencies])
-->

<!-- raises: ContainerClosedError -->

```python
with container:
    container.resolve(Settings)
# closed here: finalizers ran

# Broken
container.resolve(Settings)
```

```python
# Works: __enter__ reopens the container
with container:
    container.resolve(Settings)
```

If you did not expect the container to be closed at that point, something holds a reference to it
past its lifetime. A request handler may have kept the container from an earlier unit of work, or a
background task may still be running after the application shut down. Find where that reference
comes from and stop it outliving the container. Reopening there would hide the leak, and anything
cached after the reopen would never be finalized, because the shutdown that should close it has
already run.

A finalizer that resolves from its own container fails the same way, because the container counts
as closed while its finalizers run. That `ContainerClosedError` arrives as an entry inside the
[`FinalizerError`](finalizer-error.md) that `close_sync()` or `close_async()` raises. Do not reopen
the container from a finalizer. Give the cached instance what its finalizer needs when it is created.

## See also

- [Lifecycle: closing and reopening](../providers/lifecycle.md#closing-and-reopening) — what close
  runs and what survives a reopen.
- [Migration: To 4.x](../migration/to-4.x.md#resolving-on-a-closed-container-raises) — the 3.x
  warn-and-reopen behavior this replaced.
