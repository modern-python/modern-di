---
summary: Inlining find_provider and resolve_provider into Container.resolve is a reproduced flat ~30 ns per by-type resolve (~60 ns on 3.10), held back by a CPython 3.10 coverage-gate failure and an 8-line duplicated body that must be edited in lockstep with resolve_provider.
---

# Inline the by-type resolve entry point

`Container.resolve(dependency_type)` calls
`providers_registry.find_provider(...)` and then tail-calls
`self.resolve_provider(provider)`, paying a second Python frame on the by-type
path — the one every `@inject` marker and framework integration takes. Inlining
the `_providers.get` lookup and the `resolve_provider` body (closed guard,
`_resolvers.get` memo hit, `resolver(self)`) removes that frame.

## Why it is open

Not killed on merit. Both verifiers reproduced a flat win with genuinely flat
controls:

| path | main | candidate |
|---|---|---|
| cached hit, same scope | 181.7 ns | 152.7 ns |
| cached hit, cross-scope | 232.4 ns | 202.9 ns |
| depth-3 uncached | 588 ns | 554 ns |
| CONTROL `resolve_provider` | — | ±0.7 ns |

Roughly **-30 ns on every by-type resolve**, ~-60 ns on 3.10, and ~-83 ns per
resolve under 4-thread free-threading. An audit of all 13 sibling integration
wheels found **zero** `Container` subclasses and **zero** `resolve_provider`
overrides, so the interception-point argument that killed the `_scope_map`
inlining (see
[`../decisions/2026-08-01-scope-map-inline-declined.md`](../decisions/2026-08-01-scope-map-inline-declined.md))
does not bite here in practice today.

It is not shippable as submitted:

- **`just test-ci` fails on CPython 3.10**, a real CI matrix cell:
  `modern_di/container.py` drops 100.00% → 99.98%, with
  `_handle_recursion_error`'s call site in `resolve_provider`'s `except`
  uncovered, reproduced 5/5. 3.11 through 3.14t stay at 100%. The fix is known:
  add a test that reaches that handler **by reference** rather than through
  `resolve()`, restoring coverage at a clean call boundary instead of relying on
  near-limit cycle unwinds where 3.10 suspends the trace function. Worth noting
  the prototyper *did* run 3.10 — without coverage — which is exactly why it
  missed this.
- Two `architecture/` pages state the now-false singular and would need editing:
  `containers.md` and `validation.md` each name only `resolve_provider` as the
  path that compiles and dispatches.
- Two invariant shifts to disclose: recursion headroom moves by one frame (the
  smallest working limit for a 25-node by-type chain goes 105 → 104, the benign
  direction), and every exception raised through `resolve()` loses one traceback
  frame.

**The standing cost is the judgement call, not the measurement**: it creates a
genuinely duplicated ~8-line body that must be edited in lockstep with
`resolve_provider`, permanently, in exchange for ~30 ns. That is the trade to
rule on. A working prototype is preserved at `prototype-resolve-inline.diff` in
this session's workflow transcript directory.

## Revisit trigger

`resolve_provider`'s `RecursionError` handler gains a by-reference test so 3.10
coverage holds, **and** a maintainer accepts the duplicated body as a standing
maintenance cost. Alternatively, the by-type path shows up as a measurable
bottleneck in a real integration profile, which would settle the trade on its
own.
