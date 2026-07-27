# ContainerClosedError

**No longer raised.** As of modern-di 3.1, a container is usable immediately after construction —
there is no unopened state that raises. This page stays (every concrete `modern-di` error keeps a
troubleshooting page) to document the class's back-compat status and the warning that replaced its
failure mode.

**What changed**

Through 3.0, resolving from (or building a child of) a container that had never been opened, or one
closed after use, raised `ContainerClosedError`. As of 3.1:

- A container is **open from construction** — `closed = False` the moment `Container(...)` returns,
  with no `open()` step required and nothing to raise. `build_child_container()` never checks or
  touches any container's open/closed state — it only reads the parent's shared registries and scope
  map — and the child it returns starts open too, same as any freshly-constructed container.
- Reusing a container **after an explicit close** — `close_sync()`, `close_async()`, or exiting a
  `with`/`async with` block — self-heals the moment the container is actually resolved from, either
  directly or through a descendant whose resolve reaches back into its scope: the container reopens
  and the call succeeds, but it first emits `ContainerClosedWarning`, a `RuntimeWarning` carrying
  `.container_scope`. Building a child of that closed container does not, on its own, trigger any of
  this.
- `open()` stays available as the *explicit*, silent way to reopen a closed container — call it (or
  re-enter via `with`/`async with`) when the reuse is deliberate, so no warning fires. It runs no
  validation of its own; call `container.validate()` separately for a fail-fast check.

`ContainerClosedError` itself is kept importable for 3.x back-compat — an `except
exceptions.ContainerClosedError` clause does not break at import time — but nothing in the library
raises it anymore. It is removed in 4.0.

**What `ContainerClosedWarning` means**

Seeing it means a reference to an already-closed container was resolved from — directly, or through
a child container whose resolve reached back into the closed container's scope — without going back
through `open()`/`with` first. Two ways to respond:

- **Deliberate reuse** (e.g. a test harness or a callback-style lifecycle that closes and later
  restarts the same container object): call `container.open()`, or re-enter it with `with`/`async
  with`, before the next use — that reopens silently, with no warning, since a deliberate reopen is
  not diagnostic-worthy.
- **Unintentional reuse**: the warning is telling you a reference to the container is being held
  past its lifetime — e.g. a request handler cached the container from a previous unit of work
  instead of fetching a fresh one. Find where that reference is coming from and fix the leak instead
  of silencing the warning.

To make either path fail loudly during development, escalate the warning to an error:

```python
import warnings

from modern_di import exceptions

warnings.filterwarnings("error", category=exceptions.ContainerClosedWarning)
```

This restores 3.0's strictness for reuse-after-close (the never-opened case still self-heals
silently either way, since there is nothing to warn about there).

## See also

- [Migration: To 3.x](../migration/to-3.x.md#1-closed-containers-raise-instead-of-self-healing) — the
  3.0 behavior this page used to describe, and the 3.1 note relaxing it.
- [Lifecycle: closing and reopening](../providers/lifecycle.md#closing-and-reopening).
