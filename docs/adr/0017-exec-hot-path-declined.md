# Re-decline `exec` codegen on the resolve hot path

**Decision:** the shipped closure-compiled resolver stays the single resolve path. No `exec`-based
source-generation codegen, additive or otherwise.

The reframe that reopened this holds: `exec` is a stdlib builtin, so `dataclasses`/`attrs`-style
codegen would not touch the zero-*dependency* guarantee — "it adds a dependency" was never the real
objection. Unbundled, four claims remain:

- **Debuggability** — mitigable, but only via the attrs `linecache` discipline (script-builder,
  hygiene rules, unique-filename scheme).
- **Maintainability / audit trust** — real, no neutralizer; a fixed standing cost and a second
  mental model, independent of how small the win is.
- **Free-threading / nogil** — real, open, and modern-di-specific: it swaps captured cells for
  generated-module globals under a concurrency contract still at Beta, and cannot be retired without
  out-of-scope parallel-resolution work.
- **Deployment / `exec` bans** — mitigable via an additive fallback resolver, but that doubles the
  resolve surface and deepens the maintainability cost rather than escaping it.

**Measured**, the prize is bounded before any of that: `exec` is 0-4% faster than a hand-unrolled
closure at fixed arity (inside the noise band), with its only exclusive win — **~1.3-1.9x** —
confined to high-arity nodes and deep singleton/scoped chains, where closures already capture
~80-90% of the ceiling. Every path that neutralizes an objection pays for it in the maintainability
row, and dissolving the dependency-purity framing manufactures no win the measurement denies.

**Revisit trigger:** a user-reported, real-world resolve bottleneck on a high-arity node or a deep
singleton/scoped chain — the two forms where `exec` could pay — that the closure resolver provably
cannot close. A synthetic micro-benchmark or a hypothetical does not qualify. This is the
codegen-ceiling half of the open warm-singleton perf-headroom question.
