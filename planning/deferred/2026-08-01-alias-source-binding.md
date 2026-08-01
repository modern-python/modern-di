---
summary: Binding an Alias to its source's compiled resolver at compile time measures -36% on every alias resolve (~100 ns and 3 frames per hop); the memo-publication blocker is cleared, leaving eager compilation escaping the override front-guard as the sole prerequisite.
---

# Bind an `Alias` to its source's compiled resolver

`_compile_alias` is the only compiled closure that does not use the
`registry.resolver_for(p)` direct-reference pattern every `Factory` closure uses.
It calls `a._find_source(container)` per resolve and re-enters
`Container.resolve_provider`, paying three Python frames and two dict lookups on
every alias hop. Resolving the source once at compile time and closing over its
resolver would reduce the body to `source_resolver(container)` inside the
existing try/except that prepends the alias's resolution step.

## Why it is open

The prize is real and was reproduced by two independent verifiers: alias resolve
305.5 → 192.0 ns (**-36%**), roughly **-100 ns and -3 frames per alias hop**. A
control that overrides the alias itself stayed flat, as it must.

Two blockers, and **neither is alias-specific** — which is why this is deferred
rather than rejected.

**Eager compilation escapes the override front-guard.** Binding at compile time
makes alias compilation recursive and eager: it compiles the alias's entire
source subtree *even when the alias is overridden and the source is never
touched* — which is exactly the `modern-di-pytest` mock pattern. Shown
structurally rather than by timing: `len(providers_registry._resolvers)` after
resolving an overridden alias goes from 1 to 1+depth (11 at depth 10), and cold
cost from 6652 to 33539 ns (**+404%**). It also raises `TypeError` eagerly for a
source whose provider type `compile_resolver` does not know, and drops the
maximum pure-alias chain from 494 to 329 hops (`RecursionError` at compile time).
Any future attempt must bind **lazily on first miss**, or bind only after the
override front-guard has been cleared.

**~~The resolver-memo publication race.~~ Cleared.** The licensing invariant —
that a source registered after the alias compiles is picked up via
`_invalidate()` — was false, because `resolver_for` and `plan_for` published
their memos without checking whether a mutation had landed while they built.
Both are now generation-checked; see
[`architecture/concurrency.md`](../../architecture/concurrency.md). This blocker
no longer applies, and the first one below is the only remaining prerequisite.

A working prototype is preserved at `prototype-alias-bind.diff` in this session's
workflow transcript directory.

## Revisit trigger

Alias source binding can be made lazy enough not to compile a subtree behind an
active override. That is now the sole remaining prerequisite — resolver-memo
publication became generation-checked, closing the other one.
