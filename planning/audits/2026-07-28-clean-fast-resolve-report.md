# Clean-and-Fast Resolve Report — 2026-07-28

> Draft. Spec: planning/changes/2026-07-28.03-clean-fast-resolve-research.md

## Method and calibration

Machine: `arm64` (Apple M-series)
Python: `Python 3.14.6 (main, Jun 23 2026, 15:46:31) [Clang 22.1.3 ]`

### REPEATS calibration

The brief specifies `REPEATS = 9`. At that value the null control (Step 4) was
mostly clean but produced one noisy read on retry, and the positive control
(Step 7) produced one run where the injected effect on `g1_transient` was not
clearly separable from drift:

```
scenario                 base_ns   cand_ns   delta_%   drift_%  verdict
g1_transient               283.1     290.0     +2.41      2.37  OK
g2_cached                  129.2     137.0     +6.04      1.11  OK
```

`g1_transient`'s delta (+2.41%) barely exceeds its own drift (2.37%) — not a
readable signal. Per the brief's Step 7 instruction, `REPEATS` was raised
from 9 to 15 (edited in `.superpowers/spike/ab_bench.py`, which is
git-ignored scratch, not committed). Three repeated positive-control runs at
`REPEATS=15` then showed consistent, wide separation:

```
run 1: g1_transient +3.60 vs drift 1.60 ;  g2_cached  +9.58 vs drift 1.38
run 2: g1_transient +2.96 vs drift 1.19 ;  g2_cached +10.11 vs drift 1.67
run 3: g1_transient +3.81 vs drift 0.10 ;  g2_cached  +5.44 vs drift 0.45
```

Two repeated null-control runs at `REPEATS=15` stayed clean (no false
positives introduced by the higher `REPEATS`):

```
run 1: g1_transient delta +2.45 vs drift 1.00 ; g2_cached -0.73 vs 0.62 ; g3_chain +0.54 vs 0.82
run 2: g1_transient delta -0.23 vs drift 0.08 ; g2_cached -2.18 vs 0.53 ; g3_chain -0.64 vs 2.37
```

**Correction (review fix, 2026-07-28):** "run 2" above and the "canonical
run" table that originally followed it in this report were the same
`ab_run.sh` invocation's numbers, presented twice as if independent. That
duplication is called out here rather than silently dropped; the "Null
control" section below replaces the old canonical table with a genuinely
independent, wider measurement instead.

`REPEATS=15` is the value used for all further work in this research effort.
Per-scenario `number` (iteration counts) were not changed — `REPEATS` alone
was sufficient to make the effect readable.

### Null control across all eight g-scenarios, `REPEATS=15`

Step 4 originally exercised only `g1_transient`, `g2_cached`, `g3_chain`.
Following review, the null control was re-run across all eight g-scenarios
(`g4_wide`, `g5_cross_scope`, `g9_context`, `g12_override_active`,
`g16_by_type` added), four independent times, to get a real per-scenario
noise distribution rather than a single lucky draw. `cold`/`churn10`/`churn100`
remain out of scope for this calibration (see the floor section below).

`.superpowers/spike/ab_run.sh main main g1_transient g2_cached g3_chain g4_wide g5_cross_scope g9_context g12_override_active g16_by_type`

```
run N1:
g1_transient               278.8     282.3     +1.24      2.24  OK
g2_cached                  127.8     133.4     +4.45      0.73  OK
g3_chain                   760.0     758.0     -0.26      0.70  OK
g4_wide                   1313.5    1310.6     -0.22      0.76  OK
g5_cross_scope             336.7     336.0     -0.21      2.04  OK
g9_context                 606.2     610.8     +0.76      1.93  OK
g12_override_active       1007.6    1011.3     +0.37      0.63  OK
g16_by_type                165.7     168.7     +1.80      0.06  OK

run N2:
g1_transient               285.6     281.7     -1.36      2.56  OK
g2_cached                  129.3     128.0     -1.02      0.25  OK
g3_chain                   767.4     762.7     -0.62      2.01  OK
g4_wide                   1324.3    1330.1     +0.44      1.59  OK
g5_cross_scope             340.6     335.0     -1.64      1.71  OK
g9_context                 615.2     615.4     +0.03      1.01  OK
g12_override_active       1021.9    1007.9     -1.37      1.70  OK
g16_by_type                168.6     165.0     -2.18      0.01  OK

run N3:
g1_transient               285.1     288.0     +1.02      1.29  OK
g2_cached                  129.6     128.8     -0.60      2.69  OK
g3_chain                   768.2     769.3     +0.14      0.91  OK
g4_wide                   1319.4    1343.9     +1.86      0.85  OK
g5_cross_scope             338.4     339.2     +0.25      0.25  OK
g9_context                 615.5     615.8     +0.05      0.98  OK
g12_override_active       1003.4    1018.6     +1.51      0.07  OK
g16_by_type                168.1     169.6     +0.91      0.78  OK

run N4:
g1_transient               288.5     285.4     -1.07      0.31  OK
g2_cached                  130.9     128.1     -2.18      1.04  OK
g3_chain                   780.0     788.9     +1.15      0.67  OK
g4_wide                   1364.0    1331.6     -2.38      0.19  OK
g5_cross_scope             346.8     342.4     -1.27      0.67  OK
g9_context                 621.3     621.7     +0.06      0.40  OK
g12_override_active       1029.0    1047.8     +1.83      0.55  OK
g16_by_type                175.0     168.5     -3.70      4.20  OK
```

Every row `OK` across all four runs (base and candidate are both `main`, so
this is purely noise). But note: `verdict` here only checks `drift <=
spread_tolerance` — it says nothing about whether `delta_%` itself stayed
small. Two rows show `delta_%` well past what a 3% budget would tolerate,
*with base and candidate identical*:

- `g2_cached` hit **+4.45%** in run N1 (drift that run was only 0.73%).
- `g16_by_type` hit **-3.70%** in run N4 (drift that run was only 4.20% —
  not flagged `DISCARD` only because 4.20 happened to be the larger spread).

### Positive control (Steps 5-7) — canonical run, `REPEATS=15`

Positive control: `_probe()` (a module-level no-op) called as the first line
of `resolve_provider`, committed on throwaway branch `spike/control`
(commit `92a486f`, later deleted per Step 8).

`.superpowers/spike/ab_run.sh main spike/control g1_transient g2_cached`

```
scenario                 base_ns   cand_ns   delta_%   drift_%  verdict
g1_transient               283.1     293.9     +3.81      0.10  OK
g2_cached                  128.8     135.8     +5.44      0.45  OK
```

Both rows `OK`; both deltas clearly positive and well above drift (`g1_transient`
38x drift, `g2_cached` 12x drift). The injected ~40-60ns call-frame cost is
clearly readable on top of the ~130-290ns base for these scenarios.

### Readable-delta floor, per scenario

A later task in this research effort will judge a "clean-only" candidate as
acceptable if it costs **up to 3%** on its scenario. That judgment is only
makeable if 3% sits above the noise floor for that scenario. A single
blanket "~3%" floor (the original, now-corrected claim) hides that the floor
is not the same for every scenario — the table below states each one
plainly, from the four `REPEATS=15` null runs (N1-N4) above:

| scenario             | max \|delta\| (n=4) | max drift (n=4) | 3% separable @ REPEATS=15? |
|----------------------|---------------------|------------------|------------------------------|
| `g1_transient`       | 1.36%               | 2.56%            | Yes — comfortable margin |
| `g2_cached`          | **4.45%**           | 2.69%            | **No** — noise alone exceeded the 3% budget |
| `g3_chain`           | 1.15%               | 2.01%            | Yes — comfortable margin |
| `g4_wide`            | 2.38%               | 1.59%            | Marginal — only ~0.6pp of headroom under 3% |
| `g5_cross_scope`     | 1.64%               | 2.04%            | Yes, but thin — ~1.4pp headroom |
| `g9_context`         | 0.76%               | 1.93%            | Yes — comfortable margin, lowest-noise scenario measured |
| `g12_override_active`| 1.83%               | 1.70%            | Yes, but thin — ~1.2pp headroom |
| `g16_by_type`        | **3.70%**           | 4.20%            | **No** — noise alone exceeded the 3% budget |

**`g2_cached` and `g16_by_type` cannot adjudicate a 3% clean-only budget at
`REPEATS=15`** — a purely-noise null run produced an apparent effect larger
than the threshold a later task would use to fail a candidate. Do not soften
this: any ship/no-ship call on these two scenarios at `REPEATS=15` risks
being a false positive.

What it takes to fix it, verified empirically rather than asserted: raising
`REPEATS` from 15 to 25 for just these two scenarios and re-running the null
control three times tightened both immediately —

```
g2_cached  @ REPEATS=25: deltas +0.23%, +0.21%, -0.38%  (vs up to 4.45% @ REPEATS=15)
g16_by_type @ REPEATS=25: deltas -0.91%, +0.09%, -0.29%  (vs up to 3.70% @ REPEATS=15)
```

Recommendation for later tasks: any budget call against `g2_cached` or
`g16_by_type` at or near 3% should use `REPEATS>=25` for those two scenarios
specifically (or increase their `number` instead — not tested, but the same
lever), not the `REPEATS=15` default this task settled on for the rest of
the suite. `g4_wide`, `g5_cross_scope`, and `g12_override_active` are
separable at `REPEATS=15` but with less margin than `g1_transient`,
`g3_chain`, `g9_context` — a call landing within ~1pp of 3% on any of those
three should be re-run before being trusted.

`REPEATS=15` remains the default for this research effort's remaining
scenarios; `cold`/`churn10`/`churn100` were not covered by this calibration
pass (their base costs and variance are much larger — an earlier, unrelated
all-scenario run showed `cold`'s own `spread_pct` near 18%) and should get
their own null control before being trusted for small deltas.

## Harness hardening (post-review fix, 2026-07-28)

Review found two defects in `.superpowers/spike/ab_run.sh` (git-ignored, not
committed — the source lives only in the report):

1. **No trap.** Under `set -euo pipefail`, the final restore-to-`$START`
   line was reached only if all three measurement runs succeeded. A
   candidate revision that crashes or exits non-zero mid-scenario — exactly
   the kind of candidate this research swaps in — left its `modern_di/`
   sitting dirty in the work tree.
2. **No pre-flight dirty check.** `START="$(git rev-parse HEAD)"` captures
   only committed HEAD; invoking the script with uncommitted `modern_di/`
   edits present meant the final restore silently discarded them.

Fix: a `cleanup()` function registered via `trap cleanup EXIT INT TERM` now
owns the restore-to-`$START`, the staged-restore, and the "left dirty"
check — the only restore path, run on every exit (success, error, or
interrupt). A pre-flight `git diff --quiet HEAD -- modern_di/` guard at the
top now refuses to start if `modern_di/` is dirty at entry.

Reproduced the original bug and verified the fix in an isolated git
worktree (detached HEAD off `research/clean-fast-resolve`, harness files
copied in since `.superpowers/` is git-ignored), using a throwaway branch
`spike/crash-candidate` (off `main`) whose `resolve_provider` raises
`RuntimeError` unconditionally:

```
$ git status --short modern_di/          # before
(empty)

$ .superpowers/spike/ab_run.sh main spike/crash-candidate g1_transient
...
RuntimeError: spike: deliberate crash for ab_run.sh trap reproduction
=== script exit code: 1 ===

$ git status --short modern_di/          # after the crash
(empty)

$ git diff --quiet HEAD -- modern_di/ && echo CLEAN || echo DIRTY
CLEAN
```

The candidate crashed (exit 1) partway through the run, and `modern_di/` was
restored to `$START` and left clean — the trap fired on the non-zero exit.

Pre-flight guard, same worktree:

```
$ echo "# dirty edit" >> modern_di/container.py
$ git status --short modern_di/
 M modern_di/container.py

$ .superpowers/spike/ab_run.sh main main g1_transient
FATAL: modern_di/ has uncommitted changes; commit or stash first
=== exit code: 1 ===

$ git status --short modern_di/          # dirty edit untouched, not discarded
 M modern_di/container.py
```

The worktree and `spike/crash-candidate` branch were removed after
verification (`git worktree remove`, `git branch -D spike/crash-candidate`).
`git diff main -- modern_di/` on `research/clean-fast-resolve` remained
empty throughout — no code shipped from this fix.

## Inventory

The spec's inventory table (`planning/changes/2026-07-28.03-clean-fast-resolve-research.md`)
was a claim made by reading. Every count below was re-derived from source —
`grep -n` plus a manual read of each hit, not `grep -c` (a couple of the
brief's literal `grep -c` invocations, e.g. the `modern_di/**/*.py` glob,
either don't expand under a non-globstar shell or need `-h`/summation across
files; counting from `grep -n` output sidesteps that instead of trusting a
brittle command line).

### Copy counts, verified

| Concern | Site(s) | Spec's count | Verified count | Agrees? |
|---|---|---|---|---|
| Override front-guard | `resolver_compiler.py:95,121,216,264,290,309,329` | 6 | **7** | **No — see below** |
| Scope navigate (int compare + `_navigate`) | `resolver_compiler.py:99,126,220,268` | 4 | 4 | Yes |
| Closed-check + `_prepare()` | `resolver_compiler.py:100-101,127-128,221-222,269-270` | 4 | 4 | Yes |
| Cache-item fetch (inlined `_items.get`) | `resolver_compiler.py:227` | 1 | 1 | Yes |
| Cache sentinel check | `resolver_compiler.py:231` | 1 | 1 | Yes |
| Args build (positional / kwargs fork) | `resolver_compiler.py:102-106,129-139,175-180,197-209` | 4 bodies | 4 | Yes |
| Creator call + `CreatorCallError` routing | `resolver_compiler.py:110,143,186`; `providers/factory.py:214` | 4 | 4 | Yes |
| Error-prepend `try` | `resolver_compiler.py:104,137,178,206,296` | 5 | 5 | Yes |
| Entry dispatch (closed-check, inlined `_resolvers.get`, `RecursionError` wrap) | `container.py:215-230` | 1, per top-level resolve | 1 | Yes |

**The spec was off on the override front-guard.** Its motivation section says
the guard is "written six times", counting one guard per *provider type*
(Factory-transient, Factory-cached, Factory-unwireable, Alias,
container-provider, ContextProvider = 6). But `_compile_transient_factory`
compiles to **two** distinct closures — `resolve_positional`
(`resolver_compiler.py:91-117`) and the kwargs-fork `resolve`
(`resolver_compiler.py:119-150`) — and each carries its own independent
`if overrides.has_overrides:` guard (lines 95 and 121). `grep -n
"overrides.has_overrides" modern_di/resolver_compiler.py` returns 7 hits:
95, 121, 216, 264, 290, 309, 329. The source wins: **7 physical copies, not
6.** Any P2 prototype (Task 4) deletes 7 guards, not 6, and any "-6 copies"
claim in a later row should read "-7".

Every other row's count matches the spec exactly; nothing else needed
correction.

(For completeness, `noqa: SLF001` appears 3 times in `container.py` — lines
59, 125, 225 — and 22 times in `resolver_compiler.py`. Only a handful of
those execute per resolve call rather than once at compile time: the four
`target._prepare()` sites, the one inlined `cache_registry._items.get`, the
one `target._lock` capture read on a cache miss, and `container.py:225`'s
`registry._resolvers.get`. The rest — `f._parsed_kwargs`, `f._resolution_step`,
`f._creator`, etc. — are read once while `compile_resolver` builds the
closure, not on the hot path; the motivation section's "three private-attribute
reach-throughs" framing refers to that narrower, hot-path set.)

### Screen: rows that need no prototype

Five of the nine concerns are answered by reading alone — no A/B measurement
changes the verdict, so they are screened here rather than left `pending`.

| Concern | Movable? | Deletes copies? | New rule? | Verdict |
|---|---|---|---|---|
| Scope navigate | **No** — the target container is a runtime value (which container instance, reached via `find_container`), not decidable at compile time. The same-scope int compare is already the fast path; there is nothing further to hoist. | No | None | screened out |
| Cache-item fetch (`_items.get`) | **No** — depends on this specific container's `cache_registry._items` dict at call time, i.e. per-container runtime state | No | None | screened out |
| Cache sentinel check | **No** — same reasoning: the cached value is a runtime fact of one container instance | No | None | screened out |
| Creator call + `CreatorCallError` routing | **Partially** — the *except body* was already factored into `CreatorCallError.from_type_error` by `planning/decisions/2026-07-20-except-body-creator-error-helper.md`, for exactly this reason. The remaining four `try: return creator(...)` wrappers cannot be centralized further without adding a call frame on the hot path, which the module docstring's "hold the per-node frame at 1" invariant forbids. | No | None | collides with, and is already satisfied by, the 2026-07-20 decision |
| Error-prepend `try` | **No** — CPython 3.11+ makes an untaken `try` zero-cost at runtime, so these five are a readability/clean-only concern already, never a perf one; sharing them needs a helper call, which is the frame cost these were written to avoid | No | None | screened out |

### Four rows left `pending` for prototyping (Tasks 3-6)

| Concern | Site(s) | Verified copies | Perf |
|---|---|---|---|
| Override front-guard | `resolver_compiler.py` (7 sites, see above) | 7 | pending (P2, Task 4) |
| Closed-check + `_prepare()` | `resolver_compiler.py:100-101,127-128,221-222,269-270` | 4 | pending (P1, Task 3) — proceeds with a named behavior delta, see below |
| Args build (positional / kwargs fork) | `resolver_compiler.py:102-106,129-139,175-180,197-209` | 4 bodies | pending (P3, Task 5) |
| Entry dispatch | `container.py:215-230` (P4 targets the sibling by-type `resolve()` entry) | 1 | pending (P4, Task 6) |

### Closed-check invariant — false in general; holds under a named condition

Task 3's plan hoists `if target.closed: target._prepare()` out of the four
closures listed above and into `_navigate` alone. That is sound only if a
compiled resolver's *same-scope* branch (`target is container`, no
`_navigate` call) never meets a closed target — the entry container is
already reopened by `resolve_provider` (`container.py:217-218`), and the
only way a resolver reaches a *different* container is `_navigate`, so a
same-scope target should never need reopening.

**Baseline (Step 3):** `tests/test_spike_closed_invariant.py` — closes both
an APP container and a REQUEST child, then resolves a REQUEST-scoped
provider that depends on APP-scoped providers, and asserts both ended up
reopened.

```
$ just test tests/test_spike_closed_invariant.py -v
...
tests/test_spike_closed_invariant.py::test_closed_containers_are_reopened_before_any_node_runs PASSED [100%]
============================== 1 passed in 0.02s ===============================
```

PASSES on unmodified `main`, as expected — this is the characterization
baseline, not a red test.

**Probe (Steps 4-5):** the kwargs-fork `resolve` closure inside
`_compile_transient_factory` (`resolver_compiler.py:127-128`, the exact
site named in the brief) was temporarily changed from:

```python
        if target.closed:
            target._prepare()  # noqa: SLF001
```

to:

```python
        if target.closed and target is not container:
            target._prepare()  # noqa: SLF001
        elif target.closed:
            msg = "closed same-scope target reached a compiled resolver"
            raise AssertionError(msg)
```

Then the whole suite was run with the probe in place:

```
$ just test
...
collected 453 items
...
======================= 453 passed, 2 warnings in 0.40s ========================
```

**453 passed, 0 failed** (452 pre-existing + the 1 new spike test). No test
in the repository drives a compiled resolver's same-scope branch into a
closed target — the `AssertionError` was never raised.

**This green suite is not, by itself, evidence for the invariant.** A
suite passing on an unreached probe proves only that the existing tests
don't happen to visit that branch — not that the branch is unreachable.
(Independent review instrumented all four closed-check sites with hit
counters and reran the suite: ~1,050 resolver calls produced 5 closed-target
hits, and every one was a same-*named*-scope-but-different-*object*
cross-scope case — `test_transient_positional_warns_for_closed_cross_scope_target`,
`test_transient_kwargs_warns_for_closed_cross_scope_target`,
`test_unwireable_factory_warns_for_closed_cross_scope_target` in
`tests/providers/test_factory.py`, plus two closed-parent/open-child cases
in `tests/test_container.py` — never a same-scope one. Zero hits fired from
a same-scope branch, which is a corroborating negative, not proof of
impossibility.)

### Constructing the counterexample

Rather than resting on the suite's silence, the same-scope route was
attacked directly: a node with two dependencies, resolved in signature
order, where the first dependency's creator receives the resolving
`Container` (via the auto-registered container-provider — any creator
parameter typed `Container` wires to it automatically, per
`container.py:139-140`) and closes it as a side effect; the second
dependency is then resolved with that same container object as its
same-scope target.

```python
"""Temporary spike test: construct a same-scope closed-target counterexample."""

import dataclasses

import pytest

from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(slots=True)
class Leaf:
    pass


@dataclasses.dataclass(slots=True)
class Closer:
    pass


def make_closer(container: Container) -> Closer:
    container.close_sync()
    return Closer()


@dataclasses.dataclass(slots=True)
class Top:
    closer: Closer
    leaf: Leaf


class AppGroup(Group):
    closer = providers.Factory(creator=make_closer, scope=Scope.APP)
    leaf = providers.Factory(creator=Leaf, scope=Scope.APP)
    top = providers.Factory(creator=Top, scope=Scope.APP)


def test_dependency_closing_container_mid_resolution() -> None:
    app = Container(scope=Scope.APP, groups=[AppGroup])
    with pytest.warns(Warning) as record:
        result = app.resolve_provider(AppGroup.top)

    assert isinstance(result, Top)
```

Run against unmodified `main`:

```
$ just test tests/test_spike_mid_resolution_close.py -v -s
tests/test_spike_mid_resolution_close.py::test_dependency_closing_container_mid_resolution closed after resolve: False
warnings: ['Container (scope APP) was reused after close and has been reopened. Call `open()`, or
re-enter it with `with`/`async with`, to reuse it deliberately; if you did not intend to reuse it,
a reference is being held past its lifetime.']
PASSED
============================== 1 passed in 0.01s ===============================
```

**The counterexample constructs.** `Top`'s dependencies resolve in
signature order (`closer`, then `leaf`), both same-scope (APP), against the
same container object. `closer`'s own front-guard/closed-check passes while
the container is still open; its creator then closes it. When `leaf`'s
compiled resolver is invoked next — same-scope, no `_navigate` call — it
independently re-checks `target.closed` **on its own entry** (this is
exactly the "per-node" duplication the spec's inventory counts as
`resolver_compiler.py:100-101,127-128,221-222,269-270`), finds it closed,
warns, and reopens it before proceeding. `app.closed` is `False` again by
the time `resolve_provider` returns.

**So the invariant, stated unconditionally ("no compiled resolver ever
meets a closed same-scope target"), is false.** It survives today only
because the closed-check is duplicated into every closure and each
instance is independently defensive — the exact duplication Task 3 wants to
delete.

### What changes under Task 3's exact proposed hoist

Task 3's plan (`_navigate` reopens; the four per-closure checks are
deleted) was applied verbatim to a scratch copy of
`resolver_compiler.py` and the identical counterexample test was rerun
against it:

```
$ just test tests/test_spike_mid_resolution_close.py -v -s
FAILED: DID NOT WARN. No warnings of type (<class 'Warning'>,) were emitted.
```

Removing the `pytest.warns` assertion to observe the raw outcome:

```python
result = app.resolve_provider(AppGroup.top)
# result: Top(closer=Closer(), leaf=Leaf())
# app.closed after resolve: True
# warnings emitted: []
```

**The behavior delta, confirmed rather than assumed:** resolution still
*succeeds* — no exception, `Top` is built correctly — but silently.
`leaf`'s same-scope branch under the hoist never calls `_navigate`, so the
hoisted reopen-check (which now lives only inside `_navigate`) never runs
for it; `target.closed` is never inspected, no `ContainerClosedWarning`
fires, and the container is left `closed=True` after the top-level resolve
returns — where today it ends up `closed=False` (reopened, with a
warning). The reviewer's predicted delta ("not reopened, no warning") is
exactly what was observed.

Also confirmed: this scenario is not covered by the existing suite at all.
With the hoist applied and the spike test removed, `just test` still
reports `452 passed` — Task 3's own planned gate ("run the suite, expect
the same count as main") would not catch this delta; it would ship
unnoticed.

The hoisted `resolver_compiler.py` was reverted
(`git checkout -- modern_di/resolver_compiler.py`) and both temporary test
files were deleted; `git diff main -- modern_di/` is empty.

### Structural argument, and its residual gap

The structural case for the invariant: `resolve_provider`
(`container.py:217-218`) reopens **only the entry container**, once,
before any resolver runs. `find_container` (`container.py:165-173`)
returns `self` without constructing anything when the requested scope
equals the container's own scope, and consults `_scope_map` (ancestors
only) otherwise — so a *different* container object is returned only when
crossing a scope boundary, i.e. only via `_navigate`. Chaining these: at
the moment a top-level resolve begins, the entry container is open; any
other container object reached during that resolve is reached only
through `_navigate`, whose hoisted check (under Task 3) reopens it on
arrival. By induction over the call tree, every container object a
same-scope branch could be handed was either the just-reopened entry
container or a target just reopened by the `_navigate` call that produced
it — so it should be open.

**The gap in that induction is exactly the counterexample above:** the
argument assumes a container's `closed` state, once established at entry
or navigation time, doesn't change again before some *later* same-scope
call in the same resolve tree reuses that object. That assumption fails
whenever a creator holds a reference to its own resolving `Container` (via
the auto-registered container-provider or a stored reference to it from
context) and calls `close_sync`/`close_async` on it as a side effect
before that resolve tree finishes. No scope boundary is crossed, no new
object is created — the same object is simply mutated out from under a
later sibling call.

### Verdict

The invariant is **not unconditionally true**; it is true only under an
added condition the spec did not state: *no creator (or anything it calls)
closes the Container instance that is its own or a shared same-scope
target while that top-level resolve is still in flight.* Nothing in the
framework prevents this — depending on `Container` and calling
`close_sync`/`close_async` on it is ordinary public API, not a documented
anti-pattern, and no existing test asserts against it either way.

**Task 3 may proceed, but only with this behavior delta named explicitly,
not silently.** Recommendation, in order of preference:
1. Task 3's report row should state plainly that the hoist changes
   observable behavior in this one scenario: a same-scope target closed by
   a sibling dependency's side effect during resolution is no longer
   reopened and no longer warns; the resolve still completes, but the
   container is left closed afterward where it previously wasn't.
2. Task 3 should add a regression test capturing the **new** behavior (no
   warning, `closed` stays `True`) so a future change doesn't silently flip
   it again unnoticed — the gap here was that no test existed for either
   behavior.
3. Whether that delta is acceptable — i.e., whether "no new rule" in the
   spec's screen can still be claimed given this narrow, self-inflicted
   edge case — is a maintainer call, not mine to make unilaterally; it is
   filed as a named risk on the `P1` row rather than assumed away.

Abandoning Task 3 outright is not supported by the evidence: the delta is
narrow (requires a creator to close its own resolving container mid-flight,
which is unusual and already unwarranted by any documented contract), and
the failure mode is silent success with a stale `closed` flag, not a crash
or wrong value. But it is a real, demonstrated behavior change, and the
report must say so rather than assert a clean invariant the suite never
actually tested.

## P1 — closed-check hoist, measured (Task 3)

Applied on throwaway branch `spike/p1-closed-check` (off `main`, commit
`344ff50`): `_navigate` now reopens its own target
(`modern_di/resolver_compiler.py`), and the four per-closure copies of `if
target.closed: target._prepare()` are deleted from `resolve_positional`, the
transient factory's kwargs-fork `resolve`, the cached factory's `resolve`,
and the unwireable factory's `resolve`. Diff: `+9 -10`, one file. **-4
copies, -4 `SLF001` suppressions (net), 0 new rules.**
`git diff main -- modern_di/` on `research/clean-fast-resolve` is empty —
nothing here ships. Full raw tables live in
`.superpowers/sdd/2026-07-28-clean-fast-resolve-research/task-3-report.md`.

**Behavior delta — open, not resolved here.** This hoist is exactly the one
the counterexample above (`test_dependency_closing_container_mid_resolution`)
was built against: with the hoist applied, that scenario resolves
successfully but silently — no `ContainerClosedWarning`, and the container
is left `closed=True` where `main` reopens it and warns. `just test` passes
452/452 either way (the suite does not visit this branch), so the green run
is a sanity gate, not evidence of preservation. Whether that delta is
acceptable, and how it should be documented if so, is left as a maintainer
decision — not assumed away here.

**Perf — separates from noise on the same-scope scenarios.** Mechanism: for
a same-scope dependency the closed-check used to run unconditionally in
every closure; under the hoist it runs only inside `_navigate`, which
same-scope resolution never calls, so the check is removed from the hot path
entirely (not merely relocated). Four `REPEATS=15` runs across
`g1_transient`, `g2_cached`, `g3_chain`, `g4_wide`, `g5_cross_scope` all
verdict `OK` (no `DISCARD`). `g3_chain` (-2.4% to -3.9%) clearly clears its
1.15% null-noise ceiling from the calibration table; `g2_cached`'s `REPEATS=15`
deltas (-1.5% to -4.6%) aren't adjudicable there (its own noise floor reaches
4.45%), but three re-runs at `REPEATS=25` (-3.7% to -4.3%, drift mostly
<0.4%, vs. a <1% null band at that `REPEATS`) confirm a real effect.
`g1_transient` (-0.7% to -2.7%) mostly clears its 1.36% ceiling. `g4_wide`
(-0.3% to -2.8%) is directionally consistent but not confidently separated
from its 2.38% ceiling without a further `REPEATS` bump this task did not
run. `g5_cross_scope` (+0.4% to +0.8%) reads flat, as expected — that path
still calls `_navigate`, so its check merely relocated rather than
disappeared.

**`dis` frame count** (`TransientGroup.svc`, `resolve_positional` path):
`main` — 8 `CALL` opcodes; candidate — 7. The one fewer `CALL` is exactly
`target._prepare()`'s own call, deleted along with its guard, not a new call
introduced elsewhere; the closure stays a single flat code object either
way, so the module's "one Python frame per node" invariant holds.

**Bucket:** real, small, node-count-scaling perf win, gated on an
unresolved behavior-delta decision — not a free lunch, and not to be shipped
until the maintainer rules on whether the silent-no-warning /
stays-closed outcome for a creator that closes its own resolving container
mid-flight is acceptable.
