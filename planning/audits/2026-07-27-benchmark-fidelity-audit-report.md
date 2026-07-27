# Benchmark fidelity audit — do the benchmarks measure what they claim?

Sweep date: 2026-07-27. Subject: `benchmarks/` (guard tier), `benchmarks/comparative/`
(comparative tier), `.github/workflows/benchmarks.yml`, and
`docs/introduction/performance.md` as re-measured for 3.1.0 in
[`2026-07-27.01`](../changes/2026-07-27.01-refresh-performance-numbers.md).

Every number below was measured on the audit machine (Apple M4, macOS, CPython
3.14.6) during the sweep. Where a published figure is quoted it is from the page
as it stands after `1e9772b`.

**Verdict.** Nothing is fabricated: re-running `just bench-compare` reproduces the
published ratios closely (C1 vs dependency-injector 0.89 measured / 0.90
published; C3 vs dependency-injector 0.54 / 0.57; C4 vs wireup 0.69 / 0.69). The
defects are in *what the numbers mean*, not in whether they were taken. Two are
severe enough to invalidate a published claim (F1, F2) and one blinds a CI guard
(F1).

---

## F1 — C4 and G7 are ~93% event-loop overhead, not DI work

**Severity: high. Invalidates the published C4 column and blinds the G7 guard.**

Both scenarios call `loop.run_until_complete(...)` once per timed iteration.
That call is not free, and reusing the loop (which both do, deliberately) does
not make it free — it costs a fixed ~27 µs per entry regardless of the coroutine
body.

| measurement (modern-di, 20 000 iterations) | µs/iter |
|---|---|
| request cycle, exactly as C4/G7 time it | 29.83 |
| same cycle, N iterations inside **one** `run_until_complete` | **2.04** |
| empty coroutine through `run_until_complete` | 27.40 |

The DI work is **6.8%** of the reported number. Consequences:

- The published `C4 request lifecycle | 29.2 µs` row is ~94% asyncio floor. The
  ratio cells (dishka 1.00, that-depends 0.78, wireup 0.69) are four frameworks
  sitting on a shared constant, so real differences are compressed toward 1.0.
  In the comparative run taken during this sweep, modern-di and dishka reported
  medians of 29,167.04 ns and 29,166.93 ns — identical to the nanosecond, which
  is the floor showing through rather than a genuine tie.
- The page's claim that modern-di is "level with dishka (1.00) and faster than
  the other three" is an artifact. Amortizing the floor away does not weaken
  modern-di's position — it strengthens it (see F2).
- `benchmarks/README.md` states that for G7 "a single reused event loop keeps
  loop overhead out of the signal as far as practical". That is incorrect as
  written: loop *creation* is amortized, per-call *entry* is not.
- G7 is near-useless as a regression guard. A 2x regression in the real teardown
  path moves the reported number by ~7%, far below the workflow's 150%
  `alert-threshold` and inside run-to-run noise.

## F2 — C4 charges dependency-injector for work no other framework does

**Severity: high. Feeds the published 0.20 cell.**

`test_dependency_injector.py::test_c4_request_lifecycle` constructs
`LifecycleContainer()` *inside* the timed call — a provider-graph deepcopy —
while modern-di, dishka, that-depends, and wireup all reuse a container built in
setup. Measured:

| dependency-injector C4 | µs/iter |
|---|---|
| as benchmarked (fresh container per call) | 184.5 |
| container hoisted to setup, everything else identical | 130.6 |
| container instantiation alone | 20.1 |

~29% of its number is a cost a real dependency-injector app pays once at
startup. Note the direction: fixing F1 and F2 together makes modern-di look
*better*, not worse — stripping the 27 µs floor from both sides turns the C4
comparison against dependency-injector from ~5x into a far larger gap, because
the floor was diluting a genuine difference.

## F3 — modern-di is timed by reference; dishka and wireup are timed by type

**Severity: medium. Runs in modern-di's favour on C1–C3 vs two of four rivals.**

C1–C3 time `container.resolve_provider(Group.svc)` for modern-di, but
`container.get(Service)` for dishka and `scope.get(Service)` for wireup — those
two have no by-reference API at all. that-depends (`provider.resolve_sync()`)
and dependency-injector (`container.service()`) are by-reference like modern-di.

| modern-di, C1 graph, 500 000 iterations | ns |
|---|---|
| `resolve_provider(G.svc)` — what C1 times | 306.8 |
| `resolve(Service)` — what `dishka.get(Service)` does | 342.1 |

By-type costs +11% (the `find_provider` lookup). No single modern-di column can
be fair to both halves of the rival set.

## F4 — the comparative tier never adopted the 3.x lifecycle

**Severity: medium.**

`1b68848` made `open()` mandatory and `552f7c9` made it optional-with-implicit-
reopen. The guard tier was updated: every scenario calls `container.open()`, and
G7/G13 call `req.open()` per request as part of the measured cycle. The
comparative tier was not touched — `test_modern_di.py` calls neither. The two
tiers therefore measure different lifecycles, and the table published as
"modern-di 3.1.0" omits the per-request `open()` that the guard tier and the
docs both treat as part of a request.

## F5 — an undisclosed configuration axis: dishka locks, modern-di does not

**Severity: medium (disclosure, not correctness).**

`dishka.make_container` defaults to `lock_factory=<class '_thread.lock'>`, so
every `get()` in C1–C3 acquires a lock; `make_async_container` defaults to
`asyncio.Lock`. modern-di's cached-read path is lock-free by design. Both
frameworks run at their defaults, which is defensible — but a dishka user
targeting single-threaded work can pass `lock_factory=None`, and neither the
page nor `benchmarks/README.md` mentions the axis exists.

## F6 — the published table is not reproducible from the repo

**Severity: medium.**

`just bench-compare` prints five rows all named `test_c1_transient` with no
framework column, so a reader cannot map output to the published table. Nothing
in the repo turns benchmark output into that table; "median-of-medians over 5
runs (run-to-run variation small)" is asserted with no dispersion figure and no
committed script that computes it. "Reproduce with `just bench-compare`" is
therefore true only for someone who already knows which row is which.

## F7 — coverage gaps against what users actually pay

**Severity: medium.**

- **By-type resolution is unmeasured.** No benchmark in either tier calls
  `container.resolve(SomeType)`; every scenario resolves by provider reference.
  By-type is the path every framework integration and `@inject` call site takes.
- **Graph scale is uniformly tiny.** Every scenario runs 1–11 providers (G15's
  50 cold singletons excepted, and only for concurrency). `find_provider` and
  the registry dicts are never exercised at the 50–500 providers a real app
  registers.

## F8 — subject-class asymmetry favours modern-di

**Severity: low (~2–3% of C1/C3).**

modern-di's comparative subject graph uses `@dataclasses.dataclass(slots=True)`;
all four rivals use plain classes with a hand-written `__init__`. Construction
cost of the subject objects is inside the timed call for every framework:

| construction, 2 000 000 iterations | ns |
|---|---|
| `dataclass(slots=True)` | 39.3 |
| plain class `__init__` | 43.3 |
| `dataclass` (no slots) | 44.7 |

At C1 (2 objects) that is ~8 ns of ~334 ns; at C3 (6 objects) ~24 ns of ~833 ns.

## F9 — C5's dishka cell includes registration modern-di hoists

**Severity: low. Not published, README caveat is incomplete.**

C5 times `Provider(scope=...)` plus six `p.provide(cls)` calls inside the timed
call for dishka, while modern-di's `ChainGroup` class body is built at import
and only `Container(groups=[ChainGroup])` is timed. Measured split: provider
construction is 121.3 µs of dishka's 908.1 µs, i.e. **13%**. The README's C5
caveat covers dependency-injector's deepcopy and that-depends' import-time
wiring but not this one.

---

## Not defects

- **The concurrency harness (G14/G15) is sound.** Threads are spawned inside the
  timed call, which would normally be disqualifying, but the file pairs the
  measurement with a pure-compute control on the same harness — so the
  "resolution does not scale free-threaded" finding is not a harness artifact.
- **CI being non-gating with a 150% threshold** is the right call for
  GitHub-hosted runners; it is only a problem in combination with F1, where the
  guard cannot move enough to trip any threshold.
- **The ratios themselves reproduce.** See the verdict above.
