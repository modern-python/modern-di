# Benchmarks

Two tiers, one scenario vocabulary. Numbers here are **guidance, not published
claims**; result files are generated artifacts and are never committed.

## Guard tier (`benchmarks/`, zero external deps)

Decomposes modern-di's resolve hot path so a regression points at a specific
cost. Runs in CI (informational, non-gating) and locally via `just bench`.

| ID | Scenario | Isolates |
|----|----------|----------|
| G1 | Transient resolve, single dep, warm container | pure wiring cost |
| G2 | Cached resolve, warm cache | cache-hit lookup |
| G3 | Deep chain, depth 6, uncached | per-edge wiring |
| G4 | Wide, one object with 10 sibling deps | fan-out |
| G5 | Cross-scope resolve, REQUEST -> APP dep | `find_container` traversal |
| G6 | `build_child_container(REQUEST)` | per-request setup |
| G7 | Full lifecycle batch: K=100 x (build REQUEST -> sync-init cached resolve -> `await close_async()`) | real per-request cost incl. async teardown |
| G7c | Control: K=100 empty awaits in one loop entry | residual event-loop floor inside G7 |
| G8 | Cold first-resolve: build root container + compile + resolve, depth 6 | construction + first-compile cost |
| G9 | Context resolve: request value by type + APP dep, warm child | non-pure context-folding path |
| G10 | `validate()` on a depth-6 chain (isolated via `pedantic`) | graph-validation traversal, deep |
| G11 | `validate()` on a wide 10-sibling graph (isolated via `pedantic`) | graph-validation traversal, fan-out |
| G12 | Resolve a depth-6 chain with one unrelated override active | override front-guard (`fetch_override`) tax |
| G13 | Per-request cycle finalizing 10 cached resources (`close_sync`) | LIFO teardown at scale |
| G14 | Concurrent cached-hit throughput, N threads (lock-free read) | free-threaded read scaling |
| G15 | Concurrent first-resolve, N threads (double-checked creation lock) | free-threaded creation-lock contention |
| G16 | Warm by-type `resolve(SomeType)`, small graph | `find_provider` lookup on the integration/`@inject` path |
| G17 | Warm by-type `resolve(SomeType)`, 200-provider registry | lookup cost at realistic registry scale |

**Rules.** Containers are built/warmed in setup, never inside the timed call —
**except G8**, which builds the root container *inside* the timed call on
purpose, measuring the one-time construction + graph compile the other
scenarios amortize away.
Cold-resolve scenarios (G1, G3, G4) use transient (uncached) providers so each
timed call does the full wiring. G10/G11 use `benchmark.pedantic` with a
per-round setup that builds a fresh unvalidated container (untimed), so they
isolate `validate()` from construction — a fresh registry each round means every
round runs the full graph walk. Every benchmark asserts the resolved graph is
correct. G7 is wall-clock only — instruction-count tooling cannot measure the awaited teardown.
It times a **batch of K=100 request cycles inside a single `run_until_complete`**: one loop
entry costs ~27us on any body, which previously swamped the ~2us of real work when each
iteration entered the loop separately. Divide the G7 number by 100 for per-request cost, and
read G7c — the same batch shape with an empty body — as the residual floor still inside it
(~15% at K=100).

### Guard-tier medians sit on the platform timer's grid

Unlike the comparative tier, guard scenarios are **not** pinned to a fixed
`rounds × iterations`; pytest-benchmark calibrates each one, and the short ones land
on `iterations=1`. Their medians are therefore quantized to one tick of
`time.perf_counter` — **41 ns** on an Apple M4, and a comparable figure on any platform
(`time.get_clock_info("perf_counter").resolution`). As a share of the value that is large
for the sub-microsecond scenarios:

| Scenario | median | one tick |
|---|---|---|
| G2 cached resolve | ~180 ns | **23%** |
| G16/G17 by-type resolve | ~220-250 ns | 16-18% |
| G1 transient resolve | ~330 ns | 12% |
| G5 cross-scope | ~420 ns | 10% |
| G6/G6b child build | ~560-630 ns | 7% |
| G3 deep chain | ~830 ns | 5% |
| G4 and everything slower | ≥1.4 µs | ≤3% |

**A one-tick move is resolution, not signal.** Two runs of an unchanged G6 will happily
report 541 ns and 584 ns — exactly one tick apart, which reads as an 8% regression and is
nothing at all. This has already caused one false reading of a real change.

That is fine for what CI does with these numbers: the benchmarks workflow is non-gating
(`fail-on-alert: false`) and alerts at `150%`, i.e. a 50% regression, which no amount of
tick noise reaches. It is **not** fine for judging a small change locally. For that, measure
the specific call directly with enough iterations to escape the grid, rather than reading a
guard median:

```python
import statistics, timeit

n = 200_000
print(
    statistics.median(
        timeit.timeit(lambda: container.build_child_container(scope=Scope.REQUEST), number=n) / n * 1e9
        for _ in range(9)
    ),
    "ns",
)
```

Pinning the guard tier the way the comparative tier is pinned would remove the grid, but it
is deliberately not done: it would break the stored CI baseline every scenario is compared
against, it changes the reported statistic to a median-of-means, and each scenario would
need its own hand-tuned pair (G14 at ~1.4 ms per call cannot take the settings G2 wants).
Revisit it only if the alert threshold is ever lowered near the percentages above — then
pinning has to come first.

### Concurrency (G14/G15)

G14/G15 use a custom N-thread harness (`test_guard_concurrency.py`) — pytest-benchmark
times a parallel batch of worker threads released together behind a barrier,
parametrized over thread count `{1, 2, 4}` so the scaling trend shows within one run.
The GIL vs free-threaded (PEP 703) comparison comes from running the file under each
build (same version/arch):

```
uv run --python 3.14t --with pytest-benchmark pytest benchmarks/test_guard_concurrency.py
```

CI's guard-bench runs one GIL interpreter, so the free-threaded numbers are a manual
run. **Finding:** resolution is thread-safe but its throughput **does not scale** with
threads on a free-threaded build — cached-hit batch time is flat-to-worse as threads
rise and matches the GIL, while a pure-compute control on the same harness scales
~3.5x at 4 threads. The bottleneck is concurrent access to shared hot-path objects
(registry resolver/cache dicts, container, cached value), not the GIL; first-resolve
additionally serializes on the double-checked creation lock. Read the thread-count
*trend*, not absolutes — throughput benches are noisy and guard-bench is non-gating.

## Comparative tier (`benchmarks/comparative/`, isolated project)

modern-di vs dishka, that-depends, dependency-injector, wireup on the same
graph shape. Local-only (`just bench-compare`); never in CI. Deps are pinned in
`benchmarks/comparative/pyproject.toml`; the env is git-ignored.

| ID | Scenario | Guard equiv |
|----|----------|-------------|
| C1 | Transient resolve, single dep | G1 |
| C2 | Singleton resolve, warm | G2 |
| C3 | Deep chain, depth 6 | G3 |
| C4 | Request lifecycle: enter request scope -> sync-init resolve -> async-finalize on exit | G7 |
| C5 | Cold build + first resolve, depth 6 | G8 |
| C6 | Context: per-request runtime value by type + app dep | G9 |

### Per-framework idiomatic mapping

Each framework uses its **natural** request-scope + resource-teardown idiom (not modern-di's
scope names forced onto it). C1-C3 are synchronous resolves for every framework, and exist in
**two variants for modern-di**: by-reference (`resolve_provider`) and by-type (`resolve`).
dishka and wireup expose only by-type lookup; that-depends and dependency-injector only
by-reference. Each published row therefore compares one modern-di variant against the rivals
whose API matches it -- a single modern-di column would be unfair to one half of the set.
By-type resolution adds a fixed dict-lookup cost of roughly 40 ns on top of `resolve_provider`;
while small in absolute terms, the percentage this represents depends on the baseline, not a
framework constant. C4 is not sync-vs-sync: modern-di resolves synchronously under an
async finalizer, while dishka / that-depends / dependency-injector / wireup all force an
awaited resolve -- so C4 measures the whole request lifecycle, not an isolated resolve, and is
timed as a batch of K=100 cycles per loop entry.

| Framework (pin) | C1 transient | C2 singleton | C4 scoped + async teardown | C4 resolve |
|-----------------|--------------|--------------|----------------------------|------------|
| modern-di | `Factory` (uncached) | `Factory(cache=True)` | REQUEST `Factory(cache=CacheSettings(finalizer=async))`, `await close_async()` | **sync** |
| dishka 1.10.1 | `provide(cache=False)` | `provide` (cache default) | async-gen `@provide(REQUEST)`, `async with container()` | await |
| that-depends 4.0.2 | `Factory` | `Singleton` | async-gen `ContextResource`, `container_context` | await |
| dependency-injector 4.49.1 | `Factory` | `Singleton` | async-gen `Resource`, `init/shutdown_resources` | await |
| wireup 2.12.0 | `injectable(transient)` + scope | `injectable` (singleton default) | async-gen `injectable(scoped)`, async container | await |

**Fixed timing shape for the published scenarios (C1-C4, C6).** pytest-benchmark auto-calibrates
`iterations` per benchmark per run, which in practice left some cells at `iterations=1` -- each
median carrying a whole per-round timer pair and snapped to the platform timer's ~42 ns grid --
while others ran at 20-100 and amortized both away. A published ratio must not divide a
grid-snapped number by an unsnapped one, so C1-C4 and C6 use `benchmark.pedantic` at a shape
pinned **identically in all five files**: C1-C3 and C6 at `rounds=200, iterations=1000`, C4 at
`rounds=100, iterations=3` (C4's callable is already a batch of `K = 100` cycles, so a few
iterations put the timer pair below 0.01% of the cell). `warmup_rounds=1` replaces the warm-up
calibration used to provide; every other setup stays outside the timed call exactly as before. (C6's
later promotion did change what its timed call contains — see its caveat below.)
`tests/test_bench_report.py` parses the five files and fails if a published scenario drops off
the pinned shape or the numbers drift apart. C5 is not published on the page and stays on
auto-calibration.

Levelling this axis moved published cells **in both directions**, and the shift is not uniform:
cells that had been at `iterations=1` shed anywhere from ~10 ns (dependency-injector C1) to
~50 ns (dishka C1, C3), and one -- modern-di's by-reference C3 -- rose by ~12 ns. Because dishka
shed proportionally more than modern-di did, modern-di's C1 and C3 ratios against dishka got
*worse*, not better. Netted over the sixteen ratio cells published at the time, eight moved against
modern-di, seven for it and one was unchanged. (C6 was promoted later, so the table now
carries twenty.)
C4's estimator also shifted: a round is now the mean of `iterations` batches, so a right-skewed
distribution reports nearer its mean -- modern-di's C4 mean was 24% above its median at
`iterations=1`, and its published per-request figure rose accordingly. The mean itself did not
move (245.9 us before, 248.0 us after on the same machine), so that is a change of estimator,
not of measured work.

**Thread-safety configuration differs, at each framework's default.** dishka's `make_container`
defaults to `lock_factory=<class '_thread.lock'>`, so every `get()` in C1-C3 acquires a lock;
`make_async_container` defaults to `asyncio.Lock`. modern-di's cached-read path is lock-free by
design (see `architecture/concurrency.md`), and its creation lock is double-checked. Every
framework here runs at its default, which is the comparison a user gets out of the box -- but a
dishka user targeting single-threaded work can pass `lock_factory=None`, and that would move
dishka's C1-C3 cells. The axis is disclosed rather than normalized away.

**Caveat — C4 is not sync-vs-sync.** modern-di is the only framework that resolves
the connection **synchronously** while finalizing asynchronously; the other four
force an **awaited** resolve once the finalizer is async. C4 therefore measures the
whole request lifecycle (enter scope -> resolve -> async finalize) as wall-clock
under a shared event loop, not an isolated resolve. C1-C3 are true synchronous
resolves for every framework. wireup's transient/scoped resolves require an active
scope, entered once in setup so C1/C3 time only `scope.get`.

### C5 cold and C6 context idioms

| Framework | C5 cold (build + first resolve) | C6 context (request value by type + app dep) |
|-----------|---------------------------------|----------------------------------------------|
| modern-di | `Container(groups=[...]) + resolve` | `ContextProvider` + `build_child(context=)` |
| dishka | `Provider + provide×6 + make_container + get` | `from_context` + `container(context=)` |
| that-depends | rebuild 6 `Factory` + `resolve_sync` | `fetch_context_item_by_type` + `container_context(global_context=)` |
| dependency-injector | `ChainContainer() + c0()` | `providers.Dependency` + `.override()` |
| wireup | `create_sync_container + enter_scope + get` | `enter_scope({RequestObj: value})`, registered placeholder |

**Caveat — C5 is not one axis.** The frameworks front-load wiring at different
points, so "cold" measures different things and the cells are **not** comparable
one-to-one: modern-di / dishka / wireup time a real per-container build (dishka
builds the graph; wireup `exec`-codegens a factory per provider);
dependency-injector's number is ~98% provider-graph **deepcopy** on
instantiation, not resolution; that-depends wires at **import** and has no
per-call build, so its cell is a `Factory`-reconstruction analog (6× `Factory.__init__`
+ resolve), not a container build. dishka's cell additionally includes per-call provider registration -- `Provider(scope=...)` plus
six `provide()` calls, measured at 121.3us of its 908.1us (13%) -- which modern-di hoists to
import time in the `ChainGroup` class body. The two build cells are therefore close but not
strictly like-for-like. The honest reading is modern-di vs the
build-time codegen frameworks (dishka/wireup), where staying `exec`-free wins by
a wide margin. C5 aligns validation off (modern-di never validates unless
`validate()` is called explicitly, dishka `skip_validation=True`) so it
isolates build+compile.

**Caveat — C6 is sync for all five** (a clean sync-vs-sync comparison, unlike
C4), timing the per-request "supply value + resolve" cycle. It is **published**, against all
four rivals in one table, for C4's reason alone: modern-di resolves by reference throughout the
body and has no by-type C6 variant, so a split would leave that half mixed-basis. The rivals do
line up with the C1-C3 grouping here — that-depends resolves its C6 handler by reference, as it
does on C1-C3; only the *supply* of the request value is type-keyed, which is not the axis the
tables split on.

modern-di's C6 body was corrected in two ways when it was published, and they pull against each
other. It calls no `open()` — a freshly built child is already open as of 3.1, so timing one
charged a redundant lock acquire (81 ns, ~6% of the cell) with no counterpart in any rival body.
It now *does* close the child, because all four rivals exit a scope inside their timed bodies and
this one did not: that teardown is ~110 ns, **larger** than the `open()` removed, so on net the
correction moved modern-di's C6 cells against it, not for it. Two structural
notes: dependency-injector injects **by reference** (`providers.Dependency` +
`.override()`), not by type — a structural analog, not an equivalent; wireup
requires the runtime type **registered** as a scoped injectable with a raising
placeholder factory (its own integration idiom), the value then supplied via
`enter_scope`.

**No comparative validate() row.** `validate()` (G10/G11 in the guard tier) has
no comparative equivalent: dependency-injector and that-depends run no build-time
graph-validation pass, and for dishka and wireup validation is folded inside
`make_container` / `create_sync_container` with no isolation seam (and their C5
cold build already includes it). A cross-framework "validation cost" row would be
n/a for two frameworks and redundant for the others, so it is omitted.

## Running

- `just bench` — guard tier (this repo's env).
- `just bench-compare` — comparative tier (isolated env; first run resolves deps).
- `just bench-report [runs]` — runs the comparative tier `runs` times (default 5) and prints the
  markdown ratio table published in `docs/introduction/performance.md`. The published table is
  **generated by this command**, never hand-assembled. C4 is timed as a batch of K=100 request
  cycles per event-loop entry; the report divides by K so the published cell is per request.
