---
status: accepted
summary: Decline a per-provider compile() seam that would dissolve resolver_compiler's type-dispatch and its reaches into provider privates — one compiler makes it a hypothetical seam, and the concentrated hot-path closures are a deliberate property. Only the phantom docstrings were a real defect; those were fixed.
---

# No per-provider compile() seam

**Decision:** Do not move `resolver_compiler`'s per-type closure builders into a
`provider.compile(registry) -> resolver` method on each provider class (Card 1
of the 2026-07-17 architecture review). The `compile_resolver` type-dispatch and
its `# noqa: SLF001` reaches into `Factory`/`Alias` privates stay. The three
phantom docstrings that named dissolved interpreted methods were the one real
defect and were corrected.

## Context

The single-path compiled resolver (`2026-07-16.02`) made resolve fast by
inlining per-type closures in `resolver_compiler.py`. The review read three
things as friction: (1) `compile_resolver` dispatches on provider type with a
hardcoded `if type(provider) is Factory / Alias / ...` chain; (2) the builders
reach ~16 times into `Factory` privates (`_creator`, `_parsed_kwargs`,
`_resolution_step`, `_resolve_context_value`, `_call_creator`,
`_argument_resolution_error`) and twice into `Alias` (`SLF001`); (3) three
docstrings claimed the closures "mirror" `Factory._resolve_kwargs`,
`Alias.resolve`, and `_ContainerProvider.resolve` — methods that no longer exist.

The proposed deepening: give each provider a `compile()` method, collapsing the
dispatch to `provider.compile(registry)` and turning the private reaches into
`self.` access. Options weighed: (a) full seam — move each builder into its
provider class; (b) middle form — `compile()` extracts its own fields and hands
them to shared flat closure-builders that stay concentrated; (c) decline the
structural change and fix only the docstrings.

## Decision & rationale

Chose (c). The deciding evidence mirrors
[2026-07-15-provider-facing-seam-declined](2026-07-15-provider-facing-seam-declined.md):
**there is exactly one compiler.** `resolver_compiler` is the sole consumer of
those provider privates; nothing else varies across the proposed seam. By the
project's standing rule (one adapter = hypothetical seam, two = a real one), a
`compile()` seam is hypothetical — cleanliness, not a swap point.

Reinforcing it:

- **The `SLF001` reaches are intra-package intimacy, not a leaked abstraction.**
  The compiler co-evolves with the classes it compiles; they ship and change
  together. The markers are honest labels on a deliberate friendship, not a
  boundary violation.
- **The provider-type set is closed and tiny.** Polymorphic dispatch buys
  extensibility for types that are essentially never added; the `if type() is`
  chain over four types is not worse.
- **Concentration is a deliberate, valuable property.** Every perf-critical
  closure lives in one file, reviewed together, sharing the positional/kwargs and
  two-phase-error patterns. The full seam (a) sacrifices that; the middle form
  (b) preserves concentration only by adding a field-extraction indirection that
  earns nothing while the seam stays hypothetical.

The genuine defect was the doc-rot: three docstrings and two inline comments
named dissolved methods. Those were rewritten to describe the behavior directly
(no interpreted-path references remain), which is the whole of the fix.

## Revisit trigger

A **second consumer of provider compile-time privates** appears (a distinct
compiler, an alternate resolver backend), making `compile()` a real two-adapter
seam — **or** provider types become an open, user-extended set where adding one
must not require editing a central dispatch, at which point the polymorphic
`compile()` hook becomes the migration path.
