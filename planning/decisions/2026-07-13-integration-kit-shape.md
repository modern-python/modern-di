---
status: accepted
summary: Integration kit lives in core as low-level primitives; outliers bypass rather than the primitive absorbing them.
supersedes: null
superseded_by: null
---

# Integration kit is low-level primitives in core, and outliers bypass it

**Decision:** Extract the shared adapter skeleton into a framework-agnostic
module inside `modern-di` core, exposing only low-level primitives; genuine
outliers call core's `build_child_container` directly rather than the primitives
growing parameters to swallow them. See the design in
[changes/2026-07-13.02-integration-kit.md](../changes/2026-07-13.02-integration-kit.md).

## Context

The 13 integrations duplicate a framework-agnostic skeleton (annotation-scanning
injector + per-request child lifecycle). Options on the table for each axis:

- **Home:** core module · new `modern-di-integrations` package · status quo.
- **Interface width:** low-level primitives only · two-tier (primitives + a
  `make_inject`/child-context-manager convenience layer).
- **Outliers** (aiohttp websocket probe, grpc `set_context` split, typer
  no-context): bypass the kit · primitive absorbs them via extra parameters.

## Decision & rationale

- **In core, not a new package.** The skeleton imports only stdlib + `modern_di`,
  so it doesn't threaten core's zero-dependency stance, and it deepens the same
  `add_providers`/`resolve_dependency` seam core already blesses. A 14th repo
  would add coordinated-release cost for agnostic code every adapter already
  reaches via its `modern-di` dependency.
- **Low-level primitives only.** A `make_inject` convenience fails the deletion
  test: the adapters' wrapper shapes are *not* identical (each fetches the child
  differently — request, ASGI scope, `g`, contextvar), so the convenience must
  take a `get_container` callable and just wraps three primitives — a shallow
  module, exactly what the extraction exists to remove.
- **Outliers bypass.** Each absorbing parameter (scope-resolver callable,
  post-build `set_context` hook, no-context mode) is needed by exactly one
  adapter — a hypothetical seam, not a real one. Adding them taxes the 10
  common-case adapters and lowers depth. The outliers already call
  `build_child_container` (the real blessed primitive) directly; keeping the weird
  logic in the weird adapter is better locality.

## Addendum (2026-07-13): "bypass" is narrower than first assumed

Reading all 13 adapters concretely (not just the 4 sampled at design time)
showed only **typer** is a true Layer-1 bypass — it binds no connection at all.
aiohttp and grpc both use `bind(provider, connection)` for scope+context
derivation; they only skip `classify_connection` (aiohttp because both its
providers share one type, so isinstance can't dispatch; grpc because it has one
provider and no dispatch to do). grpc's `_build_child` collapses to one `bind()`
call, dropping its post-hoc `set_context` entirely. aiogram's context is a
multi-provider merge with a hardcoded scope — a third shape `bind()` doesn't fit
either, so it stays a two-line literal, but for a different reason than typer's
(no connection to bind) or aiohttp's (dispatch, not derivation, is the
mismatch). The **decision stands** — no primitive grew parameters to absorb any
of these — the correction is only which adapters end up calling which
primitive.

## Revisit trigger

A third adapter needs the same non-isinstance scope-dispatch (making the
"absorb it" seam real, two-adapters rule), or the convenience layer is requested
by adapter authors because the residual `inject` glue proves non-trivial in
practice.
