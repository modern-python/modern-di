# Performance

This page compares modern-di's resolution performance against four other Python
DI frameworks, states the method, and gives a command to reproduce the numbers.
modern-di has no runtime dependencies and generates no code. The comparison set
includes two frameworks that use `exec` codegen (dishka, wireup), one with a
Cython-compiled core (dependency-injector), and one pure-Python framework
(that-depends).

> Absolute timings depend on the machine and CPython build and will differ on
> yours. The ratios between frameworks are more portable across machines, so the
> table below is expressed as ratios.

## What is measured

Four scenarios, each the smallest graph that isolates one cost, run with
[`pytest-benchmark`](https://pytest-benchmark.readthedocs.io/) in an isolated
environment with pinned rival versions:

| ID | Scenario | Isolates |
|----|----------|----------|
| C1 | Transient resolve, single dependency | pure wiring cost |
| C2 | Singleton resolve, warm cache | cache-hit lookup |
| C3 | Deep chain, depth 6 | per-edge wiring |
| C4 | Request lifecycle: enter scope → resolve → async-finalize on exit | whole per-request cost |

Each framework uses its own idiomatic request-scope and resource-teardown
spelling, not modern-di's names forced onto it. Full per-framework mapping and
rules: [`benchmarks/README.md`](https://github.com/modern-python/modern-di/blob/main/benchmarks/README.md).

## Results

Measured 2026-07-27 with modern-di 3.1.0 on an Apple M4 (macOS), CPython 3.14.6,
median-of-medians over 5 runs (run-to-run variation small). Rival versions:
dishka 1.10.1, dependency-injector 4.49.1, that-depends 4.0.2, wireup 2.12.0.
Reproduce with `just bench-compare`.

The previous publication of this table ran on an Apple M2 under CPython 3.14.4,
so its absolute times are lower here for the machine, not only for the library —
compare the ratio columns across revisions of this page, not the nanoseconds.

Each cell is modern-di ÷ rival: below 1.0 (bold) means modern-di is faster,
above 1.0 means slower.

| Scenario | modern-di | vs dishka | vs dependency-injector | vs that-depends | vs wireup |
|----------|-----------|-----------|------------------------|-----------------|-----------|
| C1 transient | 375 ns | 1.28 | **0.90** | 1.12 | 1.73 |
| C2 warm singleton | 185 ns | 1.08 | 3.93 | 2.90 | 2.49 |
| C3 deep chain (6) | 875 ns | 1.75 | **0.57** | **0.78** | 1.34 |
| C4 request lifecycle | 29.2 µs | 1.00 | **0.20** | **0.78** | **0.69** |

## What the numbers show

- Against `dependency-injector`, modern-di is faster on C1, C3, and C4, and
  slower on C2. dependency-injector's warm-singleton hit (C2) is a C-level slot
  read; modern-di's is a Python dict lookup behind an override guard.
- Against `dishka` and `wireup` on the construction-heavy scenarios (C1
  transient, C3 deep chain), modern-di is roughly 1.3–1.8x slower. Both inline
  dependency calls into `exec`-generated source, which removes the per-node
  function-call frame that modern-di keeps. modern-di does not generate code (a
  [documented non-goal](design-decisions.md#non-goals)), so this difference is
  expected rather than a regression.
- On C4 (request lifecycle) modern-di is level with `dishka` (1.00) and faster
  than the other three. See the caveat below before reading the C4 column as a
  resolve-speed comparison.

**C4 is not a like-for-like resolve.** modern-di resolves the connection
synchronously while finalizing it asynchronously; the other four force an awaited
resolve once the finalizer is async. C4 therefore measures the whole request
lifecycle (enter scope → resolve → async-finalize) under a shared event loop, not
an isolated resolve. C1–C3 are synchronous resolves for every framework.

## Why the results look this way

Since 2.29.0, modern-di compiles one specialized closure per provider on first
resolve, memoized on the providers registry, replacing a generic per-call
interpreted resolver. Each compiled resolver hoists its scope navigation,
override check, and cache lookup out of the per-call path and calls its
dependencies' resolvers directly. The remaining gap to the codegen frameworks on
C1 and C3 is the per-node call frame that `exec`-inlined source removes and
modern-di keeps.

3.1.0 removed one more frame from the top of every resolve: `resolve_provider`
now opens with an inline `closed` check instead of an unconditional method call,
and `build_child_container` carries no such check at all. Measured on the guard
suite against 3.0.0 on one machine, that is worth roughly 5–11% on C1- and
C2-shaped resolves and on child construction; the deeper scenarios, which run
through compiled resolvers where the check was already inline, did not move.

## Reproduce it yourself

```bash
git clone https://github.com/modern-python/modern-di
cd modern-di
just bench-compare   # isolated env; first run resolves the pinned rival deps
```

The comparative environment is isolated and its result files are not committed,
so absolute numbers will differ from those above. The ratios are more comparable
across machines than the absolute times.

## See also

- [Comparison](comparison.md) — how modern-di compares on features.
- [Design decisions](design-decisions.md) — why resolution is sync-only and why
  `exec` codegen is a non-goal.
