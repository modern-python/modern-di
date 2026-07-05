# Design: soften `ContainerClosedError` to a self-healing deprecation

## Problem

In `2.16.0` (commit `b4c7f23`, PR #202) closing a container began setting
`closed = True`, and `resolve_provider` / `build_child_container` started raising
`ContainerClosedError` when the container is closed. Two nested provider paths
(`factory.py`, `context_provider.py`) raise it too, checked against the
container at the provider's own scope (via `find_container(self.scope)`).

Before `2.16.0`, closing only ran finalizers and cleared the cache; a subsequent
`resolve()` silently rebuilt instances, so "close then keep resolving" worked.
The new hard error is a **breaking change** that forces invasive rewrites in
downstream code (including the maintainer's own projects) built on the old
lenient behavior.

## Goal

Make the change **transitional**, not permanent: restore the lenient
"reuse-after-close works" behavior now, behind a `DeprecationWarning`, and
reinstate the hard `ContainerClosedError` as the default in `3.0`. Downstream
code keeps working today and migrates on its own schedule (wrap in `with`, or
call `open()`).

Non-goal: a `Container(strict_closed=...)` config toggle. It can be layered on
later if a programmatic strict mode is actually wanted; the Pythonic
`warnings.filterwarnings("error", ...)` escape hatch covers strictness for now.

## Design

### 1. New warning type

Add `ContainerClosedWarning(DeprecationWarning)` to `modern_di/exceptions.py`,
alongside the existing exception taxonomy. Plain subclass, no custom `__init__`,
so users can target it precisely:

```python
warnings.filterwarnings("error", category=exceptions.ContainerClosedWarning)
```

Exceptions are surfaced only as `modern_di.exceptions.*` (no top-level
re-export, no `__all__`); the warning follows the same convention.

### 2. One helper, four call sites

Add a private `Container` method:

```python
def _warn_and_reopen_if_closed(self) -> None:
    if not self.closed:
        return
    warnings.warn(
        f"Container (scope {self.scope.name}) is closed; resolving from it or building a child "
        "is deprecated and will raise ContainerClosedError in modern-di 3.0. Re-enter the "
        "container with `with`/`async with`, or call `open()`, before reusing it.",
        ContainerClosedWarning,
        stacklevel=2,
    )
    self.open()
```

Replace each of the four `if ...closed: raise ContainerClosedError(...)` sites
with a call on the correct instance:

| Site | Current | New |
|---|---|---|
| `container.py` `build_child_container` | `raise` on `self.closed` | `self._warn_and_reopen_if_closed()` |
| `container.py` `resolve_provider` | `raise` on `self.closed` | `self._warn_and_reopen_if_closed()` |
| `providers/factory.py` `resolve` | `raise` on `container.closed` | `container._warn_and_reopen_if_closed()` |
| `providers/context_provider.py` `fetch_context_value` | `raise` on `container.closed` | `container._warn_and_reopen_if_closed()` |

In the two provider sites `container` is the `find_container(self.scope)`
result, so a resolve from an **open child** whose provider resolves at a
**closed ancestor** scope heals that ancestor — matching pre-2.16 behavior.

Because the helper calls `self.open()`, resolution proceeds on an open
container and exactly **one** warning fires per close→reuse transition, not one
per resolve (no warning spam, and `.closed` is coherent after the call).

`stacklevel=2` is best-effort: the four sites sit at different call depths, so a
single stacklevel cannot pinpoint user code from all of them. The actionable
detail is the scope name carried in the message, not the reported line.

### 3. Reuse semantics unchanged

Auto-reopen is exactly today's `open()`: sets `closed = False`, leaves
`cache_registry` and `context_registry` untouched. `CacheSettings(clear_cache=False)`
instances survive the close→reopen cycle (same object returned); `clear_cache=True`
instances were finalized at close and rebuild on the next resolve. This change
only triggers the existing reopen implicitly — no new lifecycle behavior, and
`close_sync`/`close_async` (including the root's override reset) are untouched.

### 4. `ContainerClosedError` retained, unraised until 3.0

Keep the class exported and update its docstring to note it is raised in
modern-di `3.0` and is currently emitted as a `ContainerClosedWarning`. Its
message text is unchanged (it is the future 3.0 text and is intentionally
harsher than the transitional warning — "can no longer resolve … Create a new
container" is only true once the error is reinstated).

Because the class is no longer raised in the resolution flow, a direct unit test
constructs it and asserts its message and `container_scope` attribute. That
keeps it under the 100% line-coverage gate and locks the 3.0 contract.

### 5. Tests

- Flip existing `pytest.raises(ContainerClosedError)` reuse-after-close cases
  (in `tests/test_container.py`, `tests/providers/test_singleton.py`,
  `tests/providers/test_context_provider.py`) to `pytest.warns(ContainerClosedWarning)`
  and assert the call **succeeds** and `container.closed is False` afterward.
- New: only one warning per close→reuse transition (a second resolve is silent).
- New: nested closed-ancestor case (resolve from open child, provider at closed
  ancestor scope) warns once and heals.
- New: `filterwarnings("error", ContainerClosedWarning)` makes reuse raise
  (strict opt-in works).
- New: direct `ContainerClosedError` construction test (covers §4).

### 6. Docs + planning

- `architecture/containers.md` lifecycle section (currently states reuse raises
  `ContainerClosedError`) → document the transitional warn + self-heal and the
  3.0 restoration.
- `docs/providers/errors-and-exceptions.md` and `docs/providers/lifecycle.md`
  updated to match.
- Release notes at `planning/releases/2.22.0.md` (next minor after `2.21.1`).
- A `planning/changes/` bundle per the repo's planning convention, validated by
  `just check-planning`.

## Versioning

Ships in `2.22.0` — the softening is backward-compatible (code that broke on
`>=2.16.0` works again; code that relied on the error now sees a warning it can
escalate). The hard `ContainerClosedError` returns as the default in `3.0`.

## Decisions owned by the maintainer

- Target version `2.22.0`.
- `stacklevel=2` best-effort rather than threading exact frame depths per site.
- Defer the `Container(strict_closed=...)` toggle; rely on the warnings filter
  for strictness in the meantime.
