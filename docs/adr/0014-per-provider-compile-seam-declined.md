# No per-provider `compile()` seam

**Decision:** `resolver_compiler`'s per-type closure builders stay where they are; they do not move
into a `provider.compile(registry) -> resolver` method on each provider class. The
`compile_resolver` type-dispatch and its `# noqa: SLF001` reaches into `Factory`/`Alias` privates
stay.

The deciding evidence mirrors [the provider-facing seam](0012-provider-facing-seam-declined.md):
**there is exactly one compiler.** `resolver_compiler` is the sole consumer of those provider
privates and nothing varies across the proposed seam, so `compile()` is cleanliness, not a swap
point. Reinforcing it:

- **The ~16 `SLF001` reaches are intra-package intimacy, not a leaked abstraction.** The compiler
  co-evolves with the classes it compiles; they ship and change together, and the markers are honest
  labels on a deliberate friendship.
- **The provider-type set is closed and tiny.** Polymorphic dispatch buys extensibility for types
  that are essentially never added; an `if type() is` chain over four types is not worse.
- **Concentration is a deliberate property.** Every perf-critical closure lives in one file,
  reviewed together, sharing the positional/kwargs and two-phase-error patterns. The full seam
  sacrifices that; the middle form (a `compile()` that extracts fields for shared flat builders)
  preserves it only by adding an indirection that earns nothing while the seam stays hypothetical.

The one genuine defect was doc-rot: three docstrings and two inline comments named interpreted
methods that no longer existed. Those were rewritten to describe the behaviour directly, which is
the whole of the fix.

**Revisit trigger:** a **second consumer of provider compile-time privates** appears (a distinct
compiler, an alternate resolver backend), or provider types become an open, user-extended set where
adding one must not require editing a central dispatch — at which point the polymorphic `compile()`
hook becomes the migration path.
