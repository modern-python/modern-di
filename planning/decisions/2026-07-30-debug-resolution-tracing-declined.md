---
summary: Decline opt-in DEBUG resolution tracing — the `isEnabledFor` front-guard the shape depends on measures ~19ns against a ~120-140ns per-node budget, costing +11% to +37% on every resolve for every user, worst on the warm cached hit nobody opts out of.
---

# Decline opt-in DEBUG resolution tracing

**Decision:** Do not add a module-level `logging.getLogger("modern_di")` that
narrates resolution at DEBUG level. No resolution tracing ships in any form —
neither the runtime-guarded logger nor the compile-time-gated variant that would
avoid its cost.

## Context

The deferred item proposed narrating resolution at DEBUG level: resolve start,
cache hit against creator call, override short-circuit, context reads, and
finalizer order at close. Field precedent was real — Uber Fx narrates lifecycle
events, Koin exposes an opt-in `logger(Level.DEBUG)` — and both treat "why did
the container do that" as a first-class diagnostic. A *pluggable structured
event-logger subsystem* (Fx's `fxevent.Logger`, Koin's Logger abstraction) had
already been rejected against the conservative-feature-set principle; the
narrowed shape that survived was stdlib logging and nothing else.

That shape rested on one cost estimate: "one `isEnabledFor(DEBUG)` boolean per
chokepoint on the hot path, plus 5-8 log statements." The estimate was never
measured. This decision measured it.

## Decision & rationale

The guard is not a boolean. `logger.isEnabledFor(DEBUG)` is an attribute load
plus a dict lookup inside a `try`, and it measures **~19ns net** (21.2ns against
a 2.25ns loop floor) — roughly **10x** a bare module-global bool check (~1.8ns
net). Against a per-node budget of ~120-140ns, one guard is ~15% of a node, and
a cached factory needs two (resolve-start and cache-hit).

Measured by patching the shipped closures in `resolver_compiler.py` with exactly
the proposed design and re-running the guard tier, **with tracing off** — logging
never configured, i.e. the cost every user pays for a feature they never enable:

| Scenario | base | traced | delta |
|---|---|---|---|
| G2 cached resolve (warm hit) | 140 ns | 192 ns | **+37%** |
| G16 by-type resolve | 181 ns | 237 ns | **+31%** |
| G4 wide, 10 siblings | 1333 ns | 1709 ns | **+28%** |
| G17 by-type, 200-provider registry | 188 ns | 235 ns | +26% |
| G12 override active, depth 6 | 1017 ns | 1187 ns | +17% |
| G3 deep chain, depth 6 | 833 ns | 958 ns | +15% |
| G9 context resolve | 625 ns | 708 ns | +13% |
| G1 transient | 333 ns | 375 ns | +13% |
| G5 cross-scope | 375 ns | 417 ns | +11% |

Two properties make this land where it hurts most. The cost falls hardest on the
**warm cached hit** — the cheapest operation and the one the singleton pattern
makes the most common. And it **multiplies by graph size**, since every node runs
its own guards: G4's +376ns is 11 nodes each paying.

A compile-time gate was available and would have been free. Resolvers are
compiled closures memoized on the registry, and `ProvidersRegistry._invalidate()`
already exists to drop them, so `compile_resolver` could emit a traced or a plain
closure and the off-cost would be exactly zero. It was declined too, on the
feature-set principle rather than on cost: it buys back the nanoseconds by making
activation an explicit modern-di call that invalidates the resolver memo, so the
feature stops being "stdlib logging" — the one property that justified the
narrowed shape over the event subsystem already rejected — and becomes a second
public activation API plus a compile mode to keep correct forever. Paying that to
restore an estimate that measurement had already broken is not a trade worth
taking.

**Holding: decline.** Resolution stays untraced. Diagnostics remain the job of
the error messages, which already carry the resolution breadcrumb chain
(`architecture/`, since removed, and `docs/troubleshooting/`) at zero hot-path cost.

## Revisit trigger

A user-reported diagnostic dead end that the existing breadcrumb chain provably
cannot answer — a real issue where the reporter and the maintainer both failed to
determine *why* the container resolved as it did from the error alone. A
hypothetical, or a preference for narration over breadcrumbs, does not qualify.

*Measured on Python 3.14.6, Apple M4 (`perf_counter` resolution 41.67ns). Guard-tier
medians are quantized to one timer tick, so a single delta carries that granularity;
the direction and magnitude held across all nine scenarios and a repeat run.*

*Declined from the deferred item `2026-07-05-debug-resolution-tracing`.*
