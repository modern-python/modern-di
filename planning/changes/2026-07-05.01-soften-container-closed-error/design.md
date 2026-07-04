---
summary: Reuse of a closed container warns (ContainerClosedWarning) and self-reopens instead of raising; hard ContainerClosedError returns in 3.0.
---

# Design: Soften closed-container reuse to a self-healing deprecation

## Summary

The hard `ContainerClosedError` added in 2.16.0 broke "close then resolve"
code (including maintainer projects) that relied on pre-2.16 lenient behavior.
Reuse of a closed container now emits `ContainerClosedWarning` and self-reopens
so the call succeeds; the error returns as the default in 3.0. Full brainstorm
spec: `docs/superpowers/specs/2026-07-05-soften-container-closed-error-design.md`.

## Motivation

`resolve_provider` / `build_child_container` and two nested provider paths
(`factory`, `context_provider`) started raising when `closed=True`. Downstream
lifecycles that close then reuse require invasive rewrites. Making the change
transitional removes that forced migration.

## Non-goals

- A `Container(strict_closed=...)` toggle — deferred; the `warnings` filter
  covers strictness for now.
- Changing `close_sync` / `close_async` / `open` semantics.

## Design

One private `Container._warn_and_reopen_if_closed()` replaces the four
`if closed: raise` sites; it warns once and calls `self.open()`. Nested sites
call it on the `find_container(self.scope)` result, healing a closed ancestor.
`ContainerClosedError` is retained (unraised until 3.0) and covered by a direct
unit test. New `ContainerClosedWarning(DeprecationWarning)` is filterable to an
error for strict opt-in.

## Testing

Reuse-after-close tests flip from `pytest.raises(ContainerClosedError)` to
`pytest.warns(ContainerClosedWarning)` + success assertions; added tests cover
one-warning-per-cycle, nested-ancestor heal, strict opt-in, and the retained
error class. `just test-ci` stays at 100% line coverage.

## Risk

Low. Behavior is strictly more permissive than 2.16–2.21; code that expected
the error can escalate the warning. Main risk is doc drift — mitigated by the
`architecture/containers.md` promotion in this PR.
