# `resolve_provider` is not an interception seam

**Decision:** `Container.resolve_provider` is an entry point, not a hook. Overriding it in a
`Container` subclass is not a supported way to observe or intercept resolution, and the resolve path
is free to bypass it — which licenses inlining its body into `Container.resolve`, worth **-19%
(~38 ns) on every by-type resolve**, the path every `@inject` marker and framework integration takes.
`find_container` is **not** affected and remains a blessed extension point.

**It is already not a seam, and that is measurable rather than arguable.** Since the compiled
resolvers shipped in 2.29.0, a resolver calls its dependencies' resolvers directly; nothing routes a
nested node through `resolve_provider`. Its only callers are `resolve()`, `resolve_dependency()`, and
the cycle back-edge thunk in `ProvidersRegistry.resolver_for`. Demonstrated on `main` before the
change: a subclass overriding `resolve_provider` and resolving a **4-node chain** records exactly
**1** call — the top-level one. An override has never seen the graph. What a subclass can still do is
instrument the *entry points* by overriding `resolve` and `resolve_provider`, which keeps working.

**Deliberately narrower than [the `_scope_map` ruling](0024-scope-map-inline-declined.md), which
stands.** `find_container` is consulted on every cross-scope hop and the container it returns owns
the cached instance and runs its finalizer, so bypassing an override there silently relocates
lifecycle ownership — a bug, not a missed hook. Bypassing a `resolve_provider` override loses
observation, not correctness. **Field check:** an audit of all 13 sibling integration wheels found
zero `Container` subclasses and zero `resolve_provider` overrides, and `Container` subclassing was
never documented as an extension point.

**Accepted costs**, disclosed rather than discovered later: a genuinely duplicated ~8-line body
(closed check, memo hit, `resolver_for` fallback, resolver call, `RecursionError` conversion) now
lives in both `resolve` and `resolve_provider` and must be edited in lockstep — the real, permanent
price; an exception raised through `resolve()` loses one traceback frame (5 → 4); recursion headroom
moves by one frame in the benign direction.

**Consequence worth naming.** Together with
[the tracing decline](0023-debug-resolution-tracing-declined.md), modern-di offers no built-in way to
observe *per-node* resolution. That was already true — the compiled resolvers removed the last
interior call — and this records it rather than creating it.

**Revisit trigger:** a concrete request for per-resolve interception from a real integration or user.
The answer then is a designed seam with a stated contract, not a re-blessing of subclass overrides,
which the compiled resolve path stopped honouring in 2.29.0.
