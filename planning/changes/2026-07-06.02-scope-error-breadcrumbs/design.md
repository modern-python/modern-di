---
summary: Shipped ERR-3 — runtime scope errors carry breadcrumb chains naming both ends of a captive dependency, via an uncatchable empty-slots DependencyPathMixin (maintainer-ruled shape).
---

# Design: Breadcrumb dependency paths on runtime scope errors

## Summary

Implements shortlist ruling ERR-3 (2026-07-05 UX research). `Factory.resolve`
only prepends breadcrumb steps to `ResolutionError`; scope errors
(`ScopeNotInitializedError`, `ScopeSkippedError`) are `ContainerError`
subclasses raised inside `find_container`, so a runtime captive dependency
(APP factory pulling a REQUEST-scoped dep) reports only two scope names — no
provider names, no chain. The wrong-blame failure users file bugs about
elsewhere (Dagger #1023, Angular #58391); .NET MEDI names both ends.

## Approach (maintainer-ruled: mixin)

- Extract the breadcrumb machinery (`_base_message`, `dependency_path`,
  `prepend_step`, chain-rendering `__str__`) from `ResolutionError`
  (exceptions.py:148) into `DependencyPathMixin` in the same module. The
  mixin owns the two slots; `ResolutionError(DependencyPathMixin,
  ModernDIError)` keeps identical behavior; `__init__` stays cooperative
  (`super().__init__(message)` through the MRO).
- `ScopeNotInitializedError(DependencyPathMixin, ContainerError)` and
  `ScopeSkippedError(DependencyPathMixin, ContainerError)` — public base
  `ContainerError` preserved, so downstream `except ContainerError` handlers
  are unaffected. Base messages (exceptions.py:76-78, 89-93) unchanged; with
  an empty `dependency_path` the rendered message is byte-identical to today.
- Widen the two existing prepend sites from `except exceptions.ResolutionError`
  to the tuple `(ResolutionError, ScopeNotInitializedError, ScopeSkippedError)`
  (a mixin cannot be an `except` target): `factory.py:253` and the
  `Alias.resolve` except (alias.py:69-74).
- Name the failing end too (verification nuance from the report): the failing
  provider's own `find_container` call at `factory.py:244` sits outside its
  try block, so consumer frames alone would chain everything except the
  provider that actually failed. Wrap that call; on a scope error prepend
  this factory's own step, then re-raise (outer frames prepend theirs).

## Non-goals

- No change to base messages, exception bases, or attributes — only added
  chain rendering when the error propagates through resolution frames.
- No change to `validate()`'s static captive-dependency check
  (`InvalidScopeDependencyError`) — this covers the runtime path only.

## Testing

TDD in `tests/test_dependency_path.py`:
- Captive repro (the report's live-verified scenario): APP-scoped factory
  depending on a REQUEST-scoped provider, resolved from a REQUEST container —
  assert the rendered message contains both provider names, the chain arrows,
  and the scope-error base message as the `caused by:` line.
- Top-level direct resolve of a too-deep provider: message byte-identical to
  today (empty path ⇒ no chain header).
- `except ContainerError` still catches both classes.
- Alias in the chain prepends its step on a scope error.
- Full gates: `just test-ci` (100%), `just lint-ci`.

## Risk

- **Slots/MRO subtleties** (low/medium): mixin carries the slots; exception
  bases keep `__slots__ = ()`. Guarded by the byte-identical-message tests and
  the existing dependency-path suite.
- **Over-catching in the widened excepts** (low/low): the tuple is explicit;
  no other `ContainerError` subclass flows through those frames.
