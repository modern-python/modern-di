# Decline opt-in DEBUG resolution tracing

**Decision:** no module-level `logging.getLogger("modern_di")` narrating resolution at DEBUG level.
No resolution tracing ships in any form — neither the runtime-guarded logger nor the
compile-time-gated variant that would avoid its cost.

Field precedent was real (Uber Fx narrates lifecycle events, Koin exposes an opt-in
`logger(Level.DEBUG)`), and a pluggable structured event-logger subsystem had already been rejected
on the conservative-feature-set principle; the shape that survived was stdlib logging and nothing
else. It rested on one never-measured estimate: "one `isEnabledFor(DEBUG)` boolean per chokepoint."

The guard is not a boolean. `logger.isEnabledFor(DEBUG)` is an attribute load plus a dict lookup
inside a `try`, measuring **~19 ns net** (21.2 against a 2.25 ns loop floor) — roughly **10x** a bare
module-global bool check (~1.8 ns net). Against a per-node budget of ~120-140 ns, one guard is ~15%
of a node, and a cached factory needs two. Measured by patching the shipped closures with exactly
the proposed design and re-running the guard tier **with tracing off** — the cost every user pays
for a feature they never enable:

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

It lands where it hurts most: hardest on the **warm cached hit**, the cheapest operation and the one
the singleton pattern makes most common, and it multiplies by graph size, since every node runs its
own guards — G4's +376 ns is 11 nodes each paying.

A compile-time gate would have been free (resolvers are memoized closures and `_invalidate()`
already exists to drop them), and was declined on the feature-set principle rather than on cost:
activation becomes an explicit modern-di call that invalidates the resolver memo, so the feature
stops being "stdlib logging" — the one property that justified this shape over the event subsystem
already rejected — and becomes a second public activation API plus a compile mode to keep correct
forever. Diagnostics remain the job of the error messages, which already carry the resolution
breadcrumb chain (see `docs/troubleshooting/`) at zero hot-path cost.

**Revisit trigger:** a user-reported diagnostic dead end the existing breadcrumb chain provably
cannot answer — a real issue where reporter and maintainer both failed to determine *why* the
container resolved as it did from the error alone. A preference for narration over breadcrumbs does
not qualify.

*Measured on Python 3.14.6, Apple M4 (`perf_counter` resolution 41.67 ns). Guard-tier medians are
quantized to one timer tick, so a single delta carries that granularity; direction and magnitude
held across all nine scenarios and a repeat run.*
