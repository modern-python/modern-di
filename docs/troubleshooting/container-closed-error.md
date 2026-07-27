# ContainerClosedError

**No longer raised.** As of modern-di 3.1, a container is usable immediately after construction —
there is no unopened state that raises. This page stays (every concrete `modern-di` error keeps a
troubleshooting page) to document the class's back-compat status and the warning that replaced its
failure mode.

**What changed**

Through 3.0, resolving from (or building a child of) a container that had never been opened, or one
closed after use, raised `ContainerClosedError`. As of 3.1:

- A freshly-constructed container prepares itself on the first `resolve()` / `resolve_provider()` /
  `build_child_container()` call — no `open()` step required, and nothing raises.
- Reusing a container **after an explicit close** (`close_sync()`, `close_async()`, or exiting a
  `with`/`async with` block) also self-heals — the container reopens and the call succeeds — but it
  first emits `ContainerClosedWarning`, a `RuntimeWarning` carrying `.container_scope`.
- `open()` remains the fail-fast verb: call it (or enter via `with`/`async with`) to run validation
  and prepare the container up front, at startup, rather than on the first unit of work.

`ContainerClosedError` itself is kept importable for 3.x back-compat — an `except
exceptions.ContainerClosedError` clause does not break at import time — but nothing in the library
raises it anymore. It is removed in 4.0.

**What `ContainerClosedWarning` means**

Seeing it means a reference to an already-closed container was resolved from (or used to build a
child) without going back through `open()`/`with` first. Two ways to respond:

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
