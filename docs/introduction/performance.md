# Performance

modern-di is the only **zero-dependency, pure-Python** framework in its class
that holds mid-pack against `exec`-codegen and Cython-accelerated rivals. Speed
was never the pitch — [one typed wiring across every entrypoint](comparison.md)
is — but resolution is not a tax either: since the 2.29.0 compiled-closure
resolver it beats the Cython `dependency-injector` on most scenarios and ties the
codegen-based `dishka` on the async request lifecycle.

> **Read the ratios, not the nanoseconds.** Absolute timings are specific to one
> machine and one CPython build; they will differ on yours. The *ratios* between
> frameworks are the durable, portable fact — so this page leads with them.

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

Each framework uses its **own** idiomatic request-scope and resource-teardown
spelling, not modern-di's names forced onto it. Full per-framework mapping and
rules: [`benchmarks/README.md`](https://github.com/modern-python/modern-di/blob/main/benchmarks/README.md).

## Results

Measured on an Apple M2 (macOS), CPython 3.14.4, median-of-medians over 5 runs
(run-to-run variation small). Rival versions: dishka 1.10.1,
dependency-injector 4.49.1, that-depends 4.0.2, wireup 2.12.0. Reproduce with
`just bench-compare`.

Each cell is **modern-di ÷ rival** — below 1.0 (**bold**) means modern-di is
faster; above 1.0 means slower.

| Scenario | modern-di | vs dishka | vs dependency-injector | vs that-depends | vs wireup |
|----------|-----------|-----------|------------------------|-----------------|-----------|
| C1 transient | 541 ns | 1.30 | **0.81** | 1.08 | 1.77 |
| C2 warm singleton | 282 ns | 1.17 | 4.58 | 3.37 | 2.95 |
| C3 deep chain (6) | 1250 ns | 1.87 | **0.57** | **0.81** | 1.32 |
| C4 request lifecycle | 31.0 µs | 1.02 | **0.18** | **0.75** | **0.69** |

## Reading the results honestly

**Where modern-di wins.** It beats the Cython `dependency-injector` on three of
four scenarios and ties `dishka` on the C4 request lifecycle — while being the
only framework here with no compiled or generated code and no runtime
dependencies.

**Where it loses.** On construction-heavy graphs (C1 transient, C3 deep chain)
modern-di trails the `exec`-codegen frameworks `dishka` and `wireup` by roughly
1.3–1.9x. That gap is the cost of **not** generating code: both inline dependency
calls into `exec`-compiled source, removing the per-node function-call frame that
modern-di keeps. Generating code is a [deliberate non-goal](design-decisions.md#non-goals)
for a zero-dependency library, so this is an accepted floor, not a regression.

**C4 is not a like-for-like resolve.** modern-di is the only framework that
resolves the connection **synchronously** while finalizing it asynchronously; the
other four force an **awaited** resolve once the finalizer is async. C4 therefore
measures the whole request lifecycle (enter scope → resolve → async-finalize)
under a shared event loop, not an isolated resolve. C1–C3 are true synchronous
resolves for every framework.

## Why it is fast

Since 2.29.0, modern-di compiles **one specialized closure per provider** the
first time it is resolved, memoized on the providers registry. The generic,
per-call interpreted resolver is gone; each resolver hoists its scope
navigation, override check, and cache lookup out of the per-call path and calls
its dependencies' resolvers directly. That specialization captures the bulk of
the achievable speedup without generating code — the remaining gap to the
codegen leaders is the `exec` frame-inlining modern-di declines to do.

## Reproduce it yourself

```bash
git clone https://github.com/modern-python/modern-di
cd modern-di
just bench-compare   # isolated env; first run resolves the pinned rival deps
```

The comparative environment is isolated and its result files are never
committed, so your absolute numbers will differ from those above. The **ratios**
should track — that is the portable claim.

## See also

- [Comparison](comparison.md) — where modern-di fits on features, not speed.
- [Design decisions](design-decisions.md) — why resolution is sync-only and why
  `exec` codegen is a non-goal.
