---
summary: `resolve_provider` is not an interception seam and `Container` subclassing is not a supported way to intercept resolution — since the compiled resolvers landed it has only ever seen top-level calls, so inlining it into `resolve()` narrows nothing that worked.
---

# `resolve_provider` is not an interception seam

**Decision:** `Container.resolve_provider` is an entry point, not a hook. Overriding
it in a `Container` subclass is not a supported way to observe or intercept
resolution, and the resolve path is free to bypass it. This licenses inlining its
body into `Container.resolve`. `find_container` is **not** affected and remains a
blessed extension point.

## Context

Inlining `find_provider` + `resolve_provider` into `Container.resolve` measures
**-19% (~38 ns) on every by-type resolve** — the path every `@inject` marker and
framework integration takes. It was deferred partly because the same structural
objection that killed
[`2026-08-01-scope-map-inline-declined.md`](2026-08-01-scope-map-inline-declined.md)
appears to apply: `resolve_provider` is a public method on a subclassable class,
and `Container.__init__` builds children via `self.__class__`, so a subclass rides
the whole tree. Bypassing it would mean a subclass's override no longer runs for
by-type calls.

## Decision & rationale

**It is already not a seam, and that is measurable rather than arguable.** Since
the compiled resolvers shipped in 2.29.0, a resolver calls its dependencies'
resolvers *directly*; nothing routes a nested node through `resolve_provider`. Its
only callers are `resolve()`, `resolve_dependency()`, and the cycle back-edge
thunk in `ProvidersRegistry.resolver_for`. Demonstrated on `main` before this
change: a `Container` subclass overriding `resolve_provider` and resolving a
**4-node chain** records exactly **1** call — the top-level one. An override has
never seen the graph. Inlining removes one of the three top-level call sites; the
by-reference and marker-dispatch entries still route through it.

So the thing the objection protects does not exist. What a subclass can still do
after this change is instrument the *entry points* by overriding `resolve` and
`resolve_provider` — which is what someone wanting that would actually reach for,
and it keeps working.

**This is deliberately narrower than the `_scope_map` ruling, which stands.**
`find_container` is consulted on every cross-scope hop, and the container it
returns owns the cached instance and runs its finalizer — bypassing an override
there silently relocates lifecycle ownership, which is a bug, not a missed hook.
`resolve_provider` has no such consequence: bypassing an override loses
observation, not correctness. The two are not the same call and are not being
ruled on together.

**Field check.** An audit of all 13 sibling integration wheels found zero
`Container` subclasses and zero `resolve_provider` overrides. `Container`
subclassing is not documented as an extension point anywhere in `architecture/` or
`docs/`.

**Accepted costs**, disclosed rather than discovered later:

- A genuinely duplicated ~8-line body (closed check, memo hit, `resolver_for`
  fallback, resolver call, `RecursionError` conversion) now lives in both `resolve`
  and `resolve_provider` and must be edited in lockstep. This is the real price and
  it is permanent.
- An exception raised through `resolve()` loses one traceback frame (5 → 4;
  `resolve_provider` no longer appears). Verified directly.
- Recursion headroom moves by one frame in the benign direction.

**Consequence worth naming.** Together with
[`2026-07-30-debug-resolution-tracing-declined.md`](2026-07-30-debug-resolution-tracing-declined.md),
modern-di offers no built-in way to observe *per-node* resolution. That was already
true — the compiled resolvers removed the last interior call — and this decision
records it rather than creating it. Entry-point instrumentation remains available
by overriding both public entry methods.

## Revisit trigger

A concrete request for per-resolve interception from a real integration or user.
The answer then is a designed seam with a stated contract — not a re-blessing of
subclass overrides, which the compiled resolve path stopped honouring in 2.29.0.
