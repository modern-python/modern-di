# `resolve_provider` is not an interception seam

**Decision:** `Container.resolve_provider` is an entry point, not a hook. Overriding it in a
subclass is not a supported way to observe resolution, and the resolve path is free to bypass it:
`resolve()` goes type → resolver directly. `find_container` is unaffected and stays a blessed
extension point.

**Why:** since the compiled resolvers, a resolver calls its dependencies' resolvers directly and
nothing routes a nested node through `resolve_provider`; a subclass override sees exactly the
top-level call. An audit of all thirteen integration wheels found no `Container` subclass and no
override. Bypassing it loses observation, not correctness, which is what separates it from
[ADR-0024](0024-scope-map-inline-declined.md). Together with
[ADR-0023](0023-debug-resolution-tracing-declined.md) this means modern-di offers no per-node
observation of resolution; a request for one should get a designed seam with a contract, not a
re-blessing of subclass overrides.
