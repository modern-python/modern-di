# Clean-and-Fast Resolve Report — 2026-07-28

Spec: [`changes/2026-07-28.03-clean-fast-resolve-research.md`](../changes/2026-07-28.03-clean-fast-resolve-research.md)

## Summary

**The framing that commissioned this research is falsified by its own
measurements.** The spec proposed that the two axes are not opposed but share a
cause: work on the resolve path is duplicated *because* it is per-node, so a
concern moved to compile time should delete "nanoseconds and copies together."
Four candidates were prototyped and measured against that claim, and **not one
of them delivered both axes cleanly.**

- **The largest speed win made the code measurably less clean, by this
  project's own countable proxies.** P2 (compile-time override) takes the
  per-node override tax to exactly zero — `g12_override_active` **-26.5% to
  -27.5%**, the biggest effect in this effort — and deletes all 7 front-guard
  copies. But it lands at **net -15 lines** (`+37 -52`), the `noqa: SLF001`
  count **rises** 22 → 23, it falsifies four `architecture/` files (one of them
  an entire numbered design item), and it adds **8 new rules**. The guards are
  not removed so much as exchanged for a cross-registry invalidation protocol —
  a relocation of complexity, not a deletion of it. It also carries a real
  defect: an override can be lost permanently to a compile/invalidate race, in
  a split-view shape where the direct resolve returns the mock and every
  consumer returns the real object.
- **The pure cleanliness win cost multiples of its budget.** P3 (body-fork
  merge) buys no speed by construction, and costs **+9-13%** on three of its
  four named scenarios — **3-4x** the spec's own 3% clean-only budget. A
  controlled experiment attributes **55-58%** of that cost to code-object frame
  growth (11 free vars vs 5), not to the branch the merge added — so a
  branch-free reformulation recovers at most ~45% of it. The rest is inherent
  to sharing one code object across two frame shapes.
- **The one candidate shaped like the thesis in miniature rests on a false
  invariant.** P1 (closed-check hoist) does delete 4 copies and does win
  ~2.4-3.9% on deep chains and ~4% on warm singletons with no new rule named.
  But the invariant licensing it — "no compiled resolver ever meets a closed
  same-scope target" — is **false**, shown by construction rather than argued:
  a creator that closes its own resolving container mid-flight leaves a sibling
  resolving against a closed target. `main` warns and reopens it; P1 stays
  silent and leaves it closed. The suite is 452-green either way, so P1's own
  planned gate could not have caught the delta.
- **P4** (by-type entry memo) *adds* copies rather than deleting any, and
  clears only **~1.35x** against the `~2x-or-nothing` bar this repo holds
  copy-adding resolve-path changes to. Skip.

So the two axes did **not** collapse into one question. Where the removal was
genuinely one-sided (P1), the invariant licensing it did not hold. Where the
move to compile time was sound (P2), paying for it took more mechanism than it
deleted. Where cleanliness was pursued for its own sake (P3), the interpreter
charged for it in a term the spec's per-node model does not contain at all:
**closure frame size is a first-class hot-path cost on this hardware,
independent of opcodes executed** — 6-7.5% for +6 free vars / +5 locals, at
zero added executed opcodes. That term is the most portable thing this effort
learned, and "count the copies" has no room for it.

Two results survive the falsification and are worth carrying independently of
it. The **P1+P2 comparative reading** (`## What would move`): C1/C3 ratio cells
improve by 4.6x-156x their own no-code drift, and by-type warm singleton
reaches effective parity with `dishka` — a hypothetical, since both candidates
remain maintainer-gated. And the **guard-suite gap**: the committed benchmark
suite has no scenario exercising a cached-provider cold miss at all.

### Buckets

| bucket | count | rows |
|---|---|---|
| do-first | **0** | — |
| needs-decision | 3 | P1 closed-check hoist; P2 compile-time override; P3 body-fork merge |
| cleanup | **0** | — |
| skip | 1 | P4 by-type entry memo |
| screened out | 4 | scope navigate; cache-item fetch; cache sentinel; error-prepend `try` |
| already-settled | 1 | creator call + `CreatorCallError` routing |

Nine inventoried concerns, nine buckets. Two further stances are recorded
`already-settled` outside the inventory (the `exec` codegen ruling; the
APP-scoped-resolver-over-`CacheItem` deferral), and one item carries no bucket
at all because it is not a per-node concern (the guard-suite gap).

**Zero `do-first` rows is itself a finding, not an absence of one.** The spec's
routing rule made `yes / yes / nothing-new` the do-first case; exactly one
candidate reached that shape, and it reached it on an invariant that does not
hold.

### Findings at a glance

Every row's evidence — `file:line`, the three screen answers, the measured
delta with method (or the screened-out reason), the countable cleanliness
proxies, and the collision it cites — is in the per-candidate section below;
this table is the index, not the evidence.

| # | Concern & site | Movable? / deletes copies? / new rule? | Measured (A/B/A `timeit`, median of `AB_REPEATS`) | Cleanliness proxies | Collision | Bucket |
|---|---|---|---|---|---|---|
| 1 | Override front-guard — `resolver_compiler.py:95,121,216,264,290,309,329` | yes / yes, **-7** copies / **8 new rules** | `g12_override_active` **-26.5/-27.5%**; `g3_chain` -5.2/-5.5%; `g1_transient` -3.7/-4.0%; `g2_cached` -4.0/-4.8% @25. Regressions `churn1` +556%, `churn10` +49%; crossover at ~30 resolves per override cycle | net **-15** lines (`+37 -52`); `SLF001` **22→23**; 4 `architecture/` files falsified | `2026-07-18.02` licenses invalidate-on-mutation; `architecture/concurrency.md:19-20` turns load-bearing | **needs-decision** |
| 2 | Closed-check + `_prepare()` — `resolver_compiler.py:100-101,127-128,221-222,269-270` | yes / yes, **-4** copies / none *claimed* — but a demonstrated behavior delta | `g3_chain` -2.4/-3.9% (floor 1.15%); `g2_cached` -3.7/-4.3% @25; `g1_transient` -0.7/-2.7%; `g4_wide` directional only; `g5_cross_scope` flat | `+9 -10`, one file; `SLF001` **-3** net (4 deleted, 1 added in `_navigate`); `dis` 8 → 7 `CALL`, frame count still 1 | none — the invariant was assumed by the spec, never ruled on | **needs-decision** |
| 3 | Args build, positional/kwargs fork — `resolver_compiler.py:102-106,129-139,175-180,197-209` | **no** (clean-only) / yes, 4 bodies → 2 / none | `g1_transient` +10.4/+11.0%, `g3_chain` +10.0/+10.2%, `g4_wide` +11.0/+13.1%, `g9_context` +4.0/+5.3% @25, vs 0.85-1.59% floors — **3-4x the 3% budget**. Cached half below the ~1% floor | net **-39** lines (348→309); `PLR0915` -2; `C901` sites **2→3**; total `noqa` 33→31; orphans `Factory._call_creator`, `test-ci` 100% → 99.87% | the spec's own 3% clean-only trade budget, breached 3-4x | **needs-decision** |
| 4 | Entry dispatch — `container.py:215-230` | yes / **no — adds** +1 method, +1 duplicated `RecursionError` wrap, +1 memo / none | `g16_by_type` -26.14/-25.15/-26.27% (~166 → ~123 ns) = **~1.35x**, floor 2.75% @25. Controls `g1_transient`/`g2_cached` flat | net **+19** lines; `SLF001` 3→5 (**+2**); one new test required to hold the coverage gate | the `~2x-or-nothing` bar — coined at `audits/2026-07-19-perf-readability-audit-report.md:21-22` | **skip** |
| 5 | Scope navigate — `resolver_compiler.py:99,126,220,268` | **no** — the target container is a runtime value (`find_container`'s return), not a compile-time fact / n/a / n/a | screened out — nothing to hoist; the same-scope int compare is already the fast path | unchanged | — | **screened out** |
| 6 | Cache-item fetch — `resolver_compiler.py:227` | **no** — depends on this container's `cache_registry._items` at call time / n/a / n/a | screened out — per-container runtime state | unchanged | the step past it (APP-scoped resolver closing over its `CacheItem`) is deferred: `ROADMAP.md:64-68`, trigger at `deferred.md:57` untripped | **screened out** |
| 7 | Cache sentinel check — `resolver_compiler.py:231` | **no** — the cached value is a runtime fact of one container / n/a / n/a | screened out — same reasoning as row 6 | unchanged | as row 6 | **screened out** |
| 8 | Error-prepend `try` — `resolver_compiler.py:102-103,129-130,176-177,198-199,294-295` | **no** — zero-cost on 3.11+; sharing needs a call frame / n/a / n/a | screened out — clean-only on every interpreter measured (3.14/3.14t); a small real `SETUP_FINALLY` cost remains on the 3.10 floor (`pyproject.toml:5`), unmeasured here | unchanged | — | **screened out** |
| 9 | Creator call + `CreatorCallError` routing — `resolver_compiler.py:107-108,140-141,183-184`; `providers/factory.py:211-212` | **partially** — the except *body* is already centralized / no / none | not measured — already actioned: the four remaining `try: return creator(...)` wrappers cannot be shared without adding a hot-path frame, the exact cost the prior decision preserved | unchanged | `decisions/2026-07-20-except-body-creator-error-helper.md`; its revisit trigger is not tripped by anything here | **already-settled** |

### Prototype branches — kept, not deleted

The spec said prototypes "live on a throwaway spike branch and are discarded."
They were **not** discarded: reviewers re-ran measurements against them
repeatedly, and deleting them would make every number in this report
irreproducible. They are local-only and cost nothing.

| branch | tip | candidate |
|---|---|---|
| `spike/p1-closed-check` | `344ff50` | P1 — closed-check hoist |
| `spike/p2-override-compile` | `c84912a` | P2 — compile-time override |
| `spike/p3-body-merge` | `ca75df8` | P3 — body-fork merge (`f7b5556` transient half, `ca75df8` cached half) |
| `spike/p4-by-type-memo` | `8728744` | P4 — by-type entry memo (`41807dc` candidate, `8728744` its coverage test) |
| `spike/finalists` | `54a4bd8` | P1+P2 combined, for the comparative tier |

The one branch that *was* deleted is `spike/control` (`92a486f`), the
positive-control no-op probe, which had served its purpose by the end of the
calibration pass.

**No code ships from this effort.** On `research/clean-fast-resolve`, `git diff
main -- modern_di/` and `git diff main -- docs/` are both empty, and
`git status` is clean — verified at the close of this report.

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
| Error-prepend `try` | **No** — CPython 3.11+ makes an untaken `try` zero-cost at runtime, so these five are a readability/clean-only concern on every interpreter this research measured (3.14/3.14t); sharing them needs a helper call, which is the frame cost these were written to avoid. Caveat: this library's `requires-python` floor is 3.10 (`pyproject.toml:5`, tested in CI per `.github/workflows/_checks.yml:24-30`), where an untaken `try` still costs a real `SETUP_FINALLY` push/pop — small, not measured here, but not zero, so "never a perf one" is a 3.11+-only claim, not a version-general one | No | None | screened out |

### Four rows left `pending` for prototyping (Tasks 3-6)

| Concern | Site(s) | Verified copies | Perf |
|---|---|---|---|
| Override front-guard | `resolver_compiler.py` (7 sites, see above) | 7 | measured (P2, Task 4) — **needs-decision**, see below |
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
copies, -3 `SLF001` suppressions (net), 0 new rules.** (Correction, Task 9: an
earlier draft of this row said "-4 `SLF001` (net)". The real figure is **-3** —
four `# noqa: SLF001` comments are deleted with their guards, and **one is
added back** on the `target._prepare()` call hoisted into `_navigate`. Verified
on the candidate itself: `git grep -c 'noqa: SLF001' 344ff50 --
modern_di/resolver_compiler.py` returns **19**, against **22** on `main`.)
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

## P2 — compile-time override, measured both directions (Task 4)

Applied on throwaway branch `spike/p2-override-compile` (off `main`, commit
`c84912a`): `compile_resolver` reads the override set once at compile time and
returns a constant-returning resolver for an overridden provider;
`OverridesRegistry` notifies `ProvidersRegistry` to drop compiled resolvers on
every `override`/`reset_override`; and **all seven** per-closure
`if overrides.has_overrides:` front-guards are deleted. `git diff main --
modern_di/` on `research/clean-fast-resolve` is empty — nothing here ships. Full
raw tables (including the previously-missing `cold`/`churn` null calibration)
live in `.superpowers/sdd/2026-07-28-clean-fast-resolve-research/task-4-report.md`.

**Seven copies, not six** — the inventory correction above is confirmed by the
prototype: `_compile_transient_factory` compiles two hot-path closures and each
carried its own guard. **But the ledger is not a one-sided deletion.** Diff is
`+37 -52` across four files — **net only -15 lines**, because -50 lines in
`resolver_compiler.py` are bought with +19 lines of cross-registry invalidation
plumbing. `noqa: SLF001` goes **up** (22 -> 23 in the compiler, 3 -> 4 in
`container.py`): P2 adds two private reach-throughs and deletes none.

**And P2 falsifies four `architecture/` files, not one.** Under this repo's
same-PR promotion convention those rewrites are part of P2's cost:

| file | what P2 falsifies |
|---|---|
| `architecture/concurrency.md:19-20` | `override`/`reset_override` described as unlocked mutation of shared state; P2 makes that contract load-bearing |
| `architecture/resolution.md:49-58` | **the whole of numbered item 1, "Override live-guard"** — the per-node front matter, the `has_overrides` gate, and the rationale that the check "lives in each resolver rather than centrally". P2 deletes that design |
| `architecture/providers.md:85` | the compiled resolver being memoized and cleared on *registry* mutation — now false, override mutation clears it too |
| `architecture/providers.md:164` | the compiled `Alias` resolver forwarding "after its own override guard" — that guard is gone |

`resolution.md:52-54` deserves a specific note: its rationale is that *because*
the check lives in each resolver, an overridden otherwise-unwireable factory
still short-circuits to the mock. The **outcome** survives P2 (verified on both
branches — `compile_resolver` returns before dispatching to
`_compile_unwireable_factory`), but the **stated reason is falsified**. A
preserved behaviour with a dead explanation is exactly the rot the promotion
convention exists to prevent.

On the clean-code axis, then: 7 deleted guard copies, net -15 lines, +2
`noqa: SLF001`, and four architecture files needing rewrites — one of them a
whole numbered design item. This is a relocation of complexity, not a removal.

**Perf — the largest effect in this research effort, and a real regression beside
it.** `cold`/`churn10`/`churn100` had never been calibrated; a dedicated A/B/A
null control (4 runs) puts their delta floor under 0.9%, so these are quiet
scenarios, not noisy ones (Task 1's ~18% figure was within-run sample spread, not
A-to-A disagreement). Against that floor:

- Wins: `g1_transient` -3.7% to -4.0%, `g2_cached` -4.0% to -4.8% (REPEATS=25;
  unquotable at 15), `g3_chain` -5.2% to -5.5%, and **`g12_override_active`
  -26.5% to -27.5%**. G12 overrides an *unrelated* provider, so this measures
  removal of the override tax `main` charges every node of every resolve whenever
  any override exists anywhere — the state a mocked test suite is in for its whole
  run.
- Regressions: **`churn1` +556%**, **`churn10` +49%**, **`churn20` +13%**, and
  `cold` +0.1% to +2.6% (not separable from noise in every run).
- **The churn family has a crossover, so "churn regresses" is false as stated.**
  Fitting the absolutes gives a fixed **~8 us recompile per override-mutation
  cycle** against **~265 ns saved per resolve**: break-even is **~30 resolves per
  override cycle**. Below it P2 loses (`churn10` +49%), above it P2 wins
  (`churn50` -10%, `churn100` -19%). The model predicts the three points it was
  not fitted on to within 8%.
- **The churn scenarios are a hand-written *model* of a `modern-di-pytest`
  workload, not that workload** — that package lives in a sibling repository not
  in this tree. Whether a real suite sits above or below ~30 resolves per override
  is the single fact that decides whether P2 helps or hurts its target workload,
  and it is **not measured here and cannot be from this repo**.

**Free-threaded (Step 9): pass, on a confounded metric.** G14/G15 thread-count
trends are unchanged on the same `3.14t` build in one session (G14
1.00/1.88/1.93 -> 1.00/1.88/1.99; G15 1.00/1.41/2.18 -> 1.00/1.41/2.08) — both
branches flat/non-scaling, no trend regression, independently reproduced by
review. Read it as "no regression visible", not as a precise trend match:
normalising each branch to its own 1-thread median penalises a candidate that
improves the 1-thread case, which P2 does (G14 absolutes 7-12% better). The
absolute medians are the unconfounded numbers.

**Harness hazard for later tasks.** `uv run --python 3.14t ...` **rebuilds
`.venv` as free-threaded**; plain `uv run --no-sync` then silently runs on
`3.14t`. Run `just install` to restore before further GIL measurement. All A/B
numbers here predate the `3.14t` run and the two post-hoc probes were re-verified
on the restored build — but note that absolutes do *not* discriminate between
interpreters (review measured g12/churn10 on `3.14t` and landed inside the GIL
band). **What protects a number is A/B/A symmetry within one process, not that it
looks plausible.**

**Suite: green, including the gate.** `just test-ci` passes 452/452 at 100% line
coverage, and `just lint-ci` passes. No failures to enumerate. That green run is a
weak signal, so eleven interaction probes were run against `main` and P2 side by
side; nine behaviours are identical (override-after-resolve, cached-node override
and reset, dep-override vs a warm cache, `Alias`, child containers, `OverrideHandle`,
`close_sync`, `container_provider`, and refcount-only reclamation of the root).

**Three findings the suite cannot see.**

1. **An override racing a concurrent compile is lost permanently, and lost
   asymmetrically.** `resolver_for` compiles then stores, and nested
   `resolver_for` calls capture dependency resolvers **by reference**, so the
   exposed window is the *entire outermost compile* — **~8 us** for the
   7-provider graph by this task's own fitted recompile cost, and **O(graph
   size)** in general, not the two bytecodes around the memo write.
   `invalidate_resolvers` clears without the registry lock, so an `override()`
   landing anywhere in that window is overwritten by the compiling thread's
   pre-override resolver.

   The shape matters as much as the fact. With a parent mid-compile of a *later*
   sibling, its already-captured reference to the overridden child goes stale
   while the child's own memo entry is cleared and correctly recompiled —
   producing a **split view**, reproduced deterministically:

   ```
   main:  direct resolve of leaf -> 99 ; through its parent -> 99   => consistent
   P2:    direct resolve of leaf -> 99 ; through its parent ->  1   => SPLIT VIEW
   ```

   The override **works when asked for directly and fails through every
   consumer**, permanently — so the natural debugging move (resolve the
   overridden type, check it) exonerates the override. `main` self-heals because
   its guard re-reads the live dict on every resolve; P2 is **absorbing**.

   `architecture/concurrency.md:19-20` already calls this race unsafe, so the
   unsafety is not new — the failure *mode* is. **Reachability, independently
   reproduced:** uninstrumented, 200 attempts, a 120-provider graph,
   `sys.setswitchinterval(1e-6)`, GIL build — **0/200 losses on both branches**.
   It needs a genuinely slow compile or a free-threaded build to be practically
   reachable; the finding stands on shape and permanence, not frequency.

   The remedy is bigger than first sketched: a generation counter stamped only
   around the overridden node's memo write does **not** close it, because the
   stale reference is held by a parent whose compile began earlier. The counter
   must be stamped per `resolver_for` frame and re-checked before each frame's
   memo write, discarding the in-flight subtree on mismatch.
2. **Every root `close_sync`/`close_async` discards the whole compiled graph**,
   because it calls `reset_override()` unconditionally (`container.py:291`, `:299`).
   Verified against a `main` control: a container that never had an override keeps
   all 6 compiled resolvers across `close_sync` on `main`, and drops to 0 under P2. Correct, but a recompile cost `main` does not pay; narrowly fixable by
   notifying only when a mutation actually changed something.
3. **P2 splits override semantics in two, by parameter type.**
   `modern_di/providers/factory.py:183` (`_resolve_context_value`) still does a
   **live, per-resolve** `fetch_override`, untouched by P2 and — unlike the seven
   deleted front-guards — *not* gated on `has_overrides`, so it fires even with no
   override anywhere (measured: 1 call per context kwarg per warm resolve,
   identical on both branches). Two consequences. First, "after one recompile no
   node pays anything" holds for **provider-backed kwargs only**; a factory with
   `ContextProvider`-typed parameters keeps paying. Second, and worse, the same
   race that leaves a provider-backed dependency split leaves a context-backed one
   **self-healing** (`direct -> 99, through parent -> 99`). Two override semantics
   coexist in one framework, distinguished by a parameter's type and invisible at
   the call site. **`g9_context` — the one scenario exercising this path — was
   never measured for P2.**

The reference-cycle asymmetry the design requires (`ProvidersRegistry` holds the raw
overrides *dict*; `OverridesRegistry` holds the back-reference) was kept and
**verified, not assumed**: 50 populated root containers were all reclaimed with the
cycle collector disabled and `gc.collect()` found 0 — the 3.1.1 property, now shown
for the root. No finding.

**Rules P2 adds — eight, not the three the brief anticipated:**

1. Compiled resolvers are invalidated by override mutation, not only registry mutation.
2. `ProvidersRegistry` holds the raw overrides dict and `OverridesRegistry` holds a
   back-reference to it — an asymmetry that is load-bearing, since symmetrizing it
   recreates the reference cycle removed from `Container` in 3.1.1.
3. An overridden provider's resolver is a distinct compiled variant; resolver identity
   is now a function of *(provider graph, override set)*.
4. The override dict may be mutated **only** through `OverridesRegistry.override` /
   `reset_override`. Direct writes, or swapping in another `OverridesRegistry`
   post-construction, become invisible to resolution — a rule that binds sibling
   packages this repository cannot test.
5. `override`/`reset_override` racing a live resolve can lose an override
   *permanently* and *asymmetrically* (a split view: correct when resolved
   directly, stale through every consumer) — turning
   `architecture/concurrency.md:19-20` from advisory into load-bearing.
6. Every root close discards the compiled graph.
7. `has_overrides` becomes **dead public state**: three writes
   (`overrides_registry.py:14,18,27`) and **zero reads** anywhere in `modern_di/`
   on the spike, against 7 reads on `main`. It is public, documented at
   `architecture/resolution.md:53`, and the benchmark rationale at
   `benchmarks/test_guard_resolve.py:264` depends on what it does. P2 must either
   delete it (a public-surface removal) or keep a field nothing consults.
8. Override semantics split by parameter type — context-backed kwargs stay live
   and self-healing, everything else is compile-time frozen (finding 3 above).

**Bucket: `needs-decision`** — filed so regardless of the numbers, per the spec.
Three independent calls are needed before P2 could ship: whether the absorbing,
split-view override race is acceptable or must be closed with the per-frame
generation guard (a larger change than first sketched); whether two override
semantics distinguished by parameter type are acceptable, or the context path
must be brought into the compile-time scheme too; and whether the target
workload's resolves-per-override ratio clears ~30 (which requires measuring the
sibling `modern-di-pytest` repo, not this one). The four `architecture/` rewrites
above are part of the shipping cost either way.

## P3 — body-fork merge, measured against the 3% budget (Task 5)

Applied on throwaway branch `spike/p3-body-merge` (off `main`, commits
`f7b5556` transient-body merge, `ca75df8` cached-builder merge):
`_compile_transient_factory`'s two closures (`resolve_positional`, and the
kwargs-fork `resolve`) merge into one `resolve` carrying the shape as a
captured `positional` flag; `_compile_cached_factory`'s
`build_args`/`create_positional` vs `build_kwargs`/`Factory._call_creator`
selection merges the same way into one `build_cold`/`create_cold` pair.
`git diff main -- modern_di/` on `research/clean-fast-resolve` is empty —
nothing here ships. Full raw A/B/A tables, the `dis` mechanism, and the
`REPEATS`/floor methodology live in
`.superpowers/sdd/2026-07-28-clean-fast-resolve-research/task-5-report.md`.

**Unlike P1/P2, this candidate buys no speed — and the numbers show it costs
far more than the 3% it was budgeted.** Measured with a null-control floor
re-established in this session (not assumed from Task 1's): at `REPEATS=25`
the transient-body merge alone costs **+10.0% to +13.1%** on `g1_transient`,
`g3_chain`, `g4_wide` and **+4.0% to +5.3%** on `g9_context`, against
per-scenario floors of 0.85-1.59% — 3x to 15x the noise, and 3x to 4x the 3%
budget on three of the four required scenarios (independently reproduced by
review: `g1_transient` +9-12%, `g3_chain` +6-9%, `g4_wide` +12-14%, `g9_context`
+3-5%). The cached-builder merge, measured separately per the brief's staging
(Steps 6-7, plus a supplementary `g2_cold` probe added to the git-ignored
`ab_bench.py`, isolating the cached-provider cold-miss path — see the
**guard-suite gap** below for why the brief's own `cold` scenario cannot do
this), costs **below the ~1% measurement floor** — genuinely free, but it is
the smaller half of one candidate, not a separate ship decision.

**Mechanism (corrected per review) — mostly frame growth, not the branch
itself.** The first pass here attributed the cost to "~7-8 extra executed
opcodes" from checking the captured `positional` flag twice per call. Review
falsified that as the primary cause with a controlled experiment: a variant of
`main` that keeps the two-closure fork (zero executed opcodes added on the hot
path) but pads `resolve_positional`'s never-taken `except` handler so its code
object's frame shape matches the merged body's (verified identical shape,
452 tests pass) reproduced **55-58% of the regression by frame growth alone**:

| | `g1_transient` | `g4_wide` |
|---|---|---|
| `main` | 283 ns | 1348 ns |
| pad only, no branch | 301 ns (+6.4%) | 1449 ns (+7.5%) |
| P3 (full merge) | 315 ns (+11.4%) | 1525 ns (+13.1%) |

Confirmed independently here via `co_freevars`/`co_varnames`/`co_stacksize`:
`main`'s `resolve_positional` (the fork `g1_transient`/`g3_chain`/`g4_wide`'s
nodes are all on) has **5 free vars, 8 locals, stacksize 7**; `main`'s kwargs
`resolve` has 9/12/8; the merged `resolve` has **11 free vars, 13 locals,
stacksize 8** — a jump of +6 free vars / +5 locals over the positional shape,
but only +2/+1 over the kwargs shape. One shared code object now pays the
larger of the two frame shapes on every call, regardless of which branch it
takes: extra `COPY_FREE_VARS` increfs, extra `localsplus` NULL-init, and extra
decrefs at teardown, on top of the (real, but now secondary) cost of
evaluating the branch twice. **A branch-free reformulation would recover at
most ~45% of the delta** — the frame-size term is inherent to sharing one
code object across both shapes, not fixable by restructuring the branch.

**This falsifies the "fixed ~13-17ns per node, independent of scenario" model
originally reported.** `g9_context`'s smaller delta is not explained by
dilution from an untouched `ContextProvider` node (the first-pass
explanation) — it is explained by which fork the node was on in `main`.
`ContextGroup.app_dep` was `resolve_positional` (5/8, same shape as every
`g1`/`g3`/`g4` node) and pays the full frame-growth tax; `ContextGroup.handler`
was **already** the kwargs `resolve` (9/12) in `main` because it mixes a
context-provider kwarg (non-pure), so merging grows its frame by only +2/+1 and
it is close to free. Both nodes execute on every `g9_context` timed call
(`handler` calls `app_dep` as its own dependency), so the scenario's smaller
relative delta reflects a *mix* of one full-cost node and one near-free node,
not a discount from the graph shape. **The corrected model: a node's
frame-growth cost depends on which fork it was compiled to in `main` —
positional-fork nodes pay roughly the full tax, already-kwargs-fork nodes pay
a small fraction of it.** A single scenario-independent per-node constant is
false as originally stated.

**Ledger: the brief's "-2 droppable `C901`/`PLR0915` suppressions" is half
right, half backwards — verified by running `just lint-ci`, not assumed.**
`PLR0915` (statement count) does drop out on both merged functions — a
genuine -2. `C901` (cyclomatic complexity) is more nuanced than "gets worse"
as first stated: **both outer functions individually get substantially
simpler** — `_compile_transient_factory`'s own score drops 20→13,
`_compile_cached_factory`'s drops 20→18 (verified by stripping the `noqa` and
re-running `ruff check` on each side) — but neither drops *below* the
threshold-of-10 gate, so both still need a suppression, and the merge creates
one **brand-new** violation: the inner `resolve` closure inside
`_compile_transient_factory` (11>10), never flagged before because each
pre-merge half was individually under threshold on its own. Net complexity-
suppression *sites*: 2 (`main`) → 3 (candidate) — one more than before, but
driven entirely by that one new inner-closure site, not by the outer
functions getting harder to suppress (they got easier, just not easy enough).
This is a milder version of the surprise Task 4 found on `noqa: SLF001`:
merging reduces raw complexity but still relocates enough of it that nothing
becomes droppable — plus, here, it opens one new site the brief did not
anticipate. Total `noqa` occurrences do fall (33→31, `SLF001` -2 alongside the
`PLR0915` -2), and the file shrinks (348→309 lines, **net -39**, diff `+50
-89`, independently reproduced) — the cleanliness win is real, just smaller
and differently shaped than predicted.

**A cost outside the brief's stated file scope: `Factory._call_creator`
becomes dead code.** The cached factory's kwargs cold-miss path used to
reuse the shared `Factory._call_creator` bound method; the merge replaces it
with a new local closure that reimplements the identical logic inline, so
nothing in `modern_di/` calls `_call_creator` any more. `just test` still
passes 452/452 (behavior preserved), but `just test-ci` — 100% on
`main` — **fails on the candidate** at 99.87%, entirely from
`factory.py:211-219` (`_call_creator`'s body) going uncovered. A shippable
version of this merge would need a second file touched (deleting the now-dead
method) or a permanent coverage-gate exception.

**Guard-suite gap, found while isolating the cached-builder cost (corrected
per review — this is a gap in the committed guard suite, not a design flaw in
the throwaway `ab_bench.py` harness).** The brief's Step-7 scenario for this
half is `cold`, which is a faithful transcription of the repo's own canonical
G8 guard (`benchmarks/test_guard_cold.py:1-11`). But `cold`'s subject graph is
`ChainGroup` (`benchmarks/test_guard_resolve.py:82-88`), and **none of
`ChainGroup`'s providers set `cache=True`** — it is all-transient. `cold`
therefore never calls `_compile_cached_factory`'s `build_cold`/`create_cold`
at all; it measures container construction + one-time compile of six
transient resolvers + one first resolve through them, diluted by ~16us of
fixed overhead — it re-exercises the transient merge's cost, not the
cached-builder merge this stage needed to isolate. **The repo's committed
guard suite has no benchmark exercising a cached-provider cold miss at all** —
that is the actual gap, and it exists independent of this task or of
`ab_bench.py`; the supplementary `g2_cold` probe added to the git-ignored
harness works around it for this measurement only, and does not close it in
the repo. **No earlier number is invalidated by this.** Task 4 used `cold` to
measure recompilation cost, which `ChainGroup`'s six transient providers
exercise fully — its band and floors stand. Task 1's `cold` calibration is a
noise-floor measurement, unaffected either way. What is invalidated is only
the broader reading of `cold` as covering cold misses *generally* — a claim
no earlier task made; it was this task's own supplementary need for a
cached-cold-miss measurement that exposed the gap.

**Bucket: `needs-decision`.** The transient-body half breaches the 3% budget
by 3-4x on three of its four named scenarios, comfortably clear of every
measured noise floor — this alone rules out `do-first` on the numbers. The
ledger adds a second, independent reason: the predicted complexity win is
only partly realized (both outer functions get individually simpler but stay
above threshold, and the merge opens one brand-new `C901` site) and the merge
silently orphans a method, breaking the coverage gate, in a file the brief's
scope did not name. The cached-builder half is genuinely free and would be
`do-first` in isolation, but P3 is reviewed as one candidate covering both.

## P4 — by-type resolve entry memo, judged against the 2x bar (Task 6)

Applied on throwaway branch `spike/p4-by-type-memo` (off `main` `36e261f`),
commits `41807dc` (the candidate) and `8728744` (a test needed to close a
coverage gap the candidate opens — see below): `Container.resolve` memoizes a
by-type resolver lookup (`ProvidersRegistry._by_type`, cleared in
`_invalidate` alongside the other memos) and short-circuits straight to the
compiled resolver on a hit, skipping both the `find_provider` lookup and the
`resolve_provider` call frame; a memo miss falls back to
`_resolve_by_type_uncached`, which populates the memo only after a successful
resolve. `git diff main -- modern_di/` on `research/clean-fast-resolve` is
empty — nothing here ships. Full raw A/B/A tables, the frame-shape check, and
the ledger live in
`.superpowers/sdd/2026-07-28-clean-fast-resolve-research/task-6-report.md`.

**Unlike P1-P3, this candidate *adds* copies rather than deleting any** —
the brief itself flags it as the plan's only "yes/no" screen answer, held to
the `~2x-or-nothing` bar this repo already set for pure-performance changes to
the resolve path.

**Where that bar actually comes from (correction, Task 9).** The spec
(`### Screen`) and Task 6's own brief both attribute the `~2x-or-nothing` bar to
[`decisions/2026-07-19-child-lazy-alloc-declined.md`](../decisions/2026-07-19-child-lazy-alloc-declined.md).
**That file states no numeric 2x anywhere** — verified by reading it in full.
What it reports is a measured saving of `≈ 0 (0.4%)` for a caching request
cycle and `≈ 67 ns (3.5%)` for a narrow no-cache child, and it declines on
cost/risk grounds ("a resolve hot-path branch plus re-introducing the
singleton-creation race"), not against a stated multiple. The `~2x` figure was
**coined** one file over, in
[`audits/2026-07-19-perf-readability-audit-report.md:21-22`](2026-07-19-perf-readability-audit-report.md)
— "the maintainer has already set a measured ~2x-or-nothing bar for
resolve-path branching" — reading that bar *out of* the lazy-alloc decline and
into a citable rule; the spec then carried it forward from there. So the bar is
a downstream restatement of a decision that never numbered itself, and the
correct citation is the audit line, not the decision file. **P4's verdict is
unchanged either way**: 1.35x is short of ~2x, and it is equally short of the
"~0-to-3.5% is not enough to buy a hot-path branch" reasoning the decision
itself actually gives.

**Perf — real, reproducible, and well short of the bar.** `AB_REPEATS` was
raised from the harness default of 15 to 25 (`g16_by_type`'s own floor at 15
is 3.70%, per Task 1's calibration), and the null control was re-established
in this session rather than assumed from Task 1's: 4 null runs at
`REPEATS=25` put `g16_by_type`'s own floor at **2.75%** this session (looser
than Task 1's 0.91% at the same value — session noise, not a fixed constant,
matching Task 5's finding). Against that floor, 3 candidate runs gave
`g16_by_type` deltas of **-26.14%, -25.15%, -26.27%** (base ~166ns → candidate
~123ns) — 9x to 12x the floor, unambiguously real. But real is not the same as
sufficient: computed directly as a ratio, that is **~1.35x**, not ~2x — the
candidate would need to land near ~83ns to clear the bar, and it lands at
~123ns. The two required control scenarios stayed flat within their own null
floors (`g1_transient`: +1.41/-0.35/+0.03 vs a 1.80% floor; `g2_cached`:
-0.18/-1.74/+1.85 vs a 2.02% floor) — confirming the prototype does not touch
the `resolve_provider` path it was never meant to change.

**Mechanism, checked against the actual code objects, not assumed** (per Task
5's lesson that an unchecked mechanism claim is a guess): neither
`Container.resolve` nor `resolve_provider` is a closure on either branch, so
`co_freevars` is empty both sides — this is not a Task-5-style frame-growth
story. `main`'s warm path pushes two frames (`resolve`, nlocals=3, then
`resolve_provider`, nlocals=5) and does two dict lookups
(`find_provider`, then `registry._resolvers.get(provider.provider_id)`, the
second gated behind an attribute read on `provider`). P4's warm path pushes
one frame (`resolve`, nlocals=6 — `resolve_provider`'s locals folded in) and
does one dict lookup (`registry._by_type.get(dependency_type)`, keyed
directly, no attribute hop). The measured ~40ns absolute saving on a ~166ns
call is one call frame eliminated plus two dict lookups collapsed into one —
exactly what the brief's own framing predicted, and it does explain the
number; it just isn't a big enough number.

**Ledger — the brief's own prediction held exactly, source-verified, no
surprises either direction** (unlike P2's `noqa` count or P3's `C901`/dead-code
findings). `git diff main spike/p4-by-type-memo --stat -- modern_di/`: `2
files changed, 22 insertions(+), 3 deletions(-)`; file totals `container.py`
380→397 (**+17**), `providers_registry.py` 133→135 (**+2**), net **+19**
lines. `noqa: SLF001` in `container.py`: 3→5 (**+2**, exactly the two sites
the brief named). One necessary deviation from "verbatim": the brief's own
snippet's `# noqa: S101` trips `RUF100` (unused directive — this repo's
ruleset doesn't select `S`), so that one comment was dropped to keep
`just lint-ci` green; it changes nothing else in the ledger. **A cost outside
the brief's stated file scope:** the duplicated `RecursionError` wrap is
genuinely reachable (verified by construction, not dead code) only via a
*second* `container.resolve(...)` call through the warm memo whose creator
then recurses — no existing test does this (every existing recursion-guard
test fails on its *first* call, before the memo is ever populated), so
`just test-ci`'s 100%-line gate drops to 98% on `container.py` without a new
test. One was added
(`tests/test_runtime_cycle_guard.py::test_by_type_memo_hit_recursion_error_is_still_converted`,
commit `8728744`) to restore 100% coverage and confirm the wrap is live, not
dead — a file the brief's "Test: `just test`" line did not name.

**Bucket: `skip`.** Every part of the brief's own ledger prediction
materialized exactly (+1 method, +1 duplicated `RecursionError` wrap, +1 memo
to invalidate, +2 `SLF001`, plus one cost the brief didn't name — a required
test file), and the speedup is real, reproducible, and fully explained by
frame elimination — but it clears only ~1.35x against the ~2x bar (see the
attribution correction above) this
candidate is explicitly held to for adding rather than deleting copies. Both
required controls confirmed flat. Per the brief's own instruction, this is
recorded plainly as a skip rather than let an attractive double-digit
percentage carry the call.

## Screen — remaining inventory rows closed by desk analysis (Task 7)

The four rows P1-P4 did not prototype are closed here by reading — no code
changed, no A/B measurement run. `git diff main -- modern_di/` stays empty.

### Scope navigation — screened out: not movable

Unchanged from Task 2's screen (`## Inventory` above): `target = container if
container.scope == scope else _navigate(...)` decides on a runtime value —
*which* container instance `find_container` returns — not a compile-time
fact. Nothing to hoist; the same-scope int compare is already the fast path.
No new evidence from Tasks 3-6 touches this row.

### Cache-item fetch and sentinel — already-settled, with a recurring hazard

Both the `_items.get` fetch and the sentinel check were inlined in 3.1.2 and
are screened `not movable` in Task 2's table (per-container runtime state).
One step past that stays open, and it is `already-settled` rather than
`pending`: an APP-scoped resolver could close over its own `CacheItem`
directly. Quoting the collision verbatim, `ROADMAP.md:64-68`:

> A third step remains open and is **deliberately deferred**: an APP-scoped
> resolver could close over its `CacheItem` and reach ~16 ns, but the target
> is only invariant because one registry belongs to one root, so the
> registry would have to reference its root — the container reference cycle
> removed in 3.1.1. That needs a weakref and a proof, for ~30 ns.

The governing revisit trigger lives in `planning/deferred.md`, in the same
C2 warm-singleton item this ROADMAP passage continues (line 57): "**Revisit
trigger:** a user-reported warm-singleton bottleneck." This effort produced
no such report, so the deferral stands unmoved.

**Recurrence, not just a citation.** Task 4 (P2) met the identical hazard
from the opposite direction while designing `OverridesRegistry`'s link to
`ProvidersRegistry`, and routed around it the same way this deferred item
would need to: it gave `ProvidersRegistry` the raw overrides *dict* rather
than a reference to the `OverridesRegistry` object, precisely so the two
registries would not reference each other (this report, P2 section: "the raw
overrides dict... asymmetry that is load-bearing, since symmetrizing it
recreates the reference cycle removed from `Container` in 3.1.1" —
rule 2 of "Rules P2 adds"). Two unrelated candidates, designed by different
tasks against different registries, independently hit the same wall and
made the same choice (a one-way reference, never a two-way one) to avoid
resurrecting the 3.1.1 cycle. That recurrence is itself the finding: it is
evidence that "no registry may hold a reference back to a structure that
can reach its own root" is a real, recurring constraint on this design
space, not an incidental detail of one deferred idea. Any future attempt at
the APP-scoped-resolver-over-`CacheItem` idea should expect to need the same
weakref-and-proof shape P2 avoided needing at all, and should read P2's
choice as a precedent before re-deriving it.

### Creator-call and error-prepend `try` blocks — clean-only on 3.11+; a real, small cost remains on the 3.10 floor

CPython 3.11+ zero-cost exceptions mean an untaken `try` costs nothing at
runtime on that interpreter range (no setup opcode, no frame-table entry
executed on the success path). But `pyproject.toml:5` sets `requires-python
= ">=3.10,<4"`, and `.github/workflows/_checks.yml:24-30` runs the test
matrix down to 3.10 — a version this library still ships and tests. On 3.10,
`try` still lowers to a `SETUP_FINALLY` block-stack push/pop, a small but
real executed cost. So the accurate claim is narrower than "never perf": on
every interpreter version this research measured on (3.14/3.14t) both rows
are clean-code concerns only, with nothing to hoist at runtime — but on the
3.10 floor this library still supports, an untaken `try` is not free, so
"never" overstates it. No measurement in this research exercised 3.10, so
this is a version-support fact noted for accuracy, not a re-opened perf row.

**Creator-call + `CreatorCallError` routing** collides with
`planning/decisions/2026-07-20-except-body-creator-error-helper.md`, which
already centralized the *except body* — the `tb_next` discriminate, the
`CreatorCallError` construction, `prepend_step` — into
`CreatorCallError.from_type_error`, called from inside each site's `except
TypeError:` block, for exactly this reason. Quoting its rationale verbatim:
"The success (hot) path stays `return creator(*args)` byte-for-byte — no
frame is restored." What remains uncentralized are the four `try: return
creator(...)` wrappers themselves — `resolver_compiler.py:107-108,140-141,183-184`
and `providers/factory.py:211-212` (the `try:`/`return creator(...)` or
`return self._creator(...)` line pairs, not the `except` bodies quoted
above, which are the centralized code) — those cannot be shared without
adding a call frame around the creator call on every resolve, which is the
exact cost the 2026-07-17.02 drift-lock bundle rejected a whole-call helper
to avoid, and which the 2026-07-20 decision's own scope (except-body only)
declined to reopen. Its revisit trigger — "the resolve hot path regresses
after this lands... or a future change needs the creator-call rule to
differ per site again" — is not tripped by anything in this research: P1-P4
left this code path untouched, and no per-site divergence in the rule was
found. Decision stands.

**Error-prepend `try`** — `resolver_compiler.py:102-103,129-130,176-177,198-199,294-295`
(the `try:` line and its first body line at each of the 5 sites; the
`except _STEP_ERRORS as exc:` lines Task 2's copy-count table anchors on are
104/137/178/206/296) — has no comparable
decision to collide with: it was already screened `not movable` in Task 2's
table on the same zero-cost-exception reasoning, and nothing in Tasks 3-6
bears on it. Restated here only because the brief asked for every remaining
row to get an explicit verdict rather than being left to imply one from
Task 2's table: screened out, clean-only on 3.11+ (see the 3.10 caveat
above), unchanged.

**Correction (Task 9) to the anchor-offset aside.** An earlier draft of the
parenthetical above said the `except` anchors are "one line past each of" the
`try:`/first-body pairs. That is true for **3 of the 5 sites**, not all five —
verified against live source with `grep -n "try:\|except _STEP_ERRORS"
modern_di/resolver_compiler.py`:

| `try:` / first body | `except _STEP_ERRORS` | offset |
|---|---|---|
| 102-103 | 104 | 1 line past |
| **129-130** | **137** | **7** — multi-statement try body |
| 176-177 | 178 | 1 line past |
| **198-199** | **206** | **7** — multi-statement try body |
| 294-295 | 296 | 1 line past |

The two 7-line offsets are the kwargs-fork builders, whose `try` bodies build a
whole kwargs dict rather than a single expression. Both sets of line numbers
were already correct; only the "one line past" generalization about how they
relate was wrong.

### `exec` codegen stance — not prototyped; one indirect, suggestive lead from Task 5

Reopened by maintainer ruling (`planning/decisions/2026-07-19-exec-hot-path-declined.md`),
so it gets a row rather than silence, even though this effort built no `exec`
prototype. The decision's bound stands as written: 0-4% faster than a
hand-unrolled closure at fixed arity (inside the noise band), with its only
exclusive win — ~1.3-1.9x — confined to high-arity nodes and deep
singleton/scoped chains. Its revisit trigger, quoted verbatim: "A
user-reported, real-world resolve bottleneck on a high-arity node or a deep
singleton/scoped chain — the two forms where `exec` could pay — that the
closure resolver provably cannot close. A synthetic micro-benchmark or a
hypothetical does not qualify." This effort produced no user-reported
bottleneck — only synthetic guard-tier benchmarks — so by the decision's own
stated terms this is not a qualifying trigger. **The ruling stands unmoved.**
P1 through P4 together are the cheaper half of that same 0-4%/1.3-1.9x
ceiling: closure-level cleanups reachable without a second code-generation
mechanism.

That said, Task 5 (P3) measured something that bears on the *size* of the
codegen prize, worth recording as a lead even though it does not move the
ruling. Task 5 merged two compiled closures into one and measured a
regression larger than predicted; a controlled follow-up experiment isolated
the cause rather than assuming it. It built a variant of `main` that kept
the original two-closure fork (zero extra opcodes executed on the hot path)
but padded the never-taken `except` handler in `resolve_positional` so its
code object's frame shape matched the merged closure's — same free-variable
count, same locals count, verified via `co_freevars`/`co_varnames`. That
pad-only variant, with no branching added, reproduced **55-58% of the full
merge's regression** on its own:

| | `g1_transient` | `g4_wide` |
|---|---|---|
| `main` | 283 ns | 1348 ns |
| pad only, no branch | 301 ns (+6.4%) | 1449 ns (+7.5%) |
| P3 (full merge) | 315 ns (+11.4%) | 1525 ns (+13.1%) |

So: **closure frame growth alone costs 6-7.5% on this hardware, in the
direction of fewer captured free variables being faster** (the merged
closure's 11 free vars / 13 locals against the original positional-fork
closure's 5 free vars / 8 locals is what the pad recreated — more
`COPY_FREE_VARS` increfs, more `localsplus` NULL-init, more decrefs at
teardown, all per call).

The connection to `exec` codegen: modern-di's resolvers are closures over
captured cells, while `exec`-based codegen (the kind `dishka`/`wireup` use,
per the competitor-perf research this decision cites) generates flat
function source that can inline constants directly and reference module
globals instead of closing over cells — it need not pay the free-variable
frame-shape cost the pad-only experiment isolated. So Task 5's controlled
experiment, built for an unrelated question (diagnosing P3's own
regression), accidentally measured the **sign and rough scale of one term**
that `exec` codegen would act on: going from a closure's captured-cell frame
shape to a flat generated function's global/constant-reference shape is
*plausibly* worth something in the same 6-7.5% neighborhood this hardware
showed for *shrinking* free-variable count within a closure.

**What this is not.** It is not a measurement of `exec` — no `exec`-generated
code was written or run anywhere in this research. It says nothing about
`exec`'s other costs (source generation and `compile()` at startup, the
`linecache` hygiene the decision's debuggability analysis requires, the
free-threading exposure of module-global reads replacing captured-cell
reads) or about whether the effect composes linearly across a whole resolve
chain rather than one node. It bounds nothing — the existing decision's 0-4%
figure was derived from an actual `exec` vs. closure comparison in the
competitor-perf research and is not superseded by this indirect reading.
Confirming or refuting the connection needs an actual `exec` prototype
compiled and measured against the same guard scenarios, which this effort
did not build and which the decision's revisit trigger does not currently
license. **Recorded as a lead with its evidence attached, for whoever next
reopens this stance — not as a refutation of the current ruling.**

### Guard-suite gap (not a per-node concern, filed here so it is not lost)

Task 5, while isolating the cached-builder half of P3's merge, found that
the committed guard suite has **no benchmark exercising a cached-provider
cold miss at all**: `benchmarks/test_guard_cold.py`'s `cold` scenario
transcribes G8 faithfully, but its subject graph (`ChainGroup`,
`benchmarks/test_guard_resolve.py:82-88`) is all-transient — none of its
providers set `cache=True` — so `cold` never reaches
`_compile_cached_factory`'s `build_cold`/`create_cold` builders. A future
change to those builders could ship with `cold` green and nothing in the
committed suite would notice. This is not a per-graph-node cost like the
rest of this inventory, so it does not get a movability/perf verdict of its
own — it is recorded here because it was surfaced by this research and
belongs in the same document as the rest of the inventory closure, so the
next sweep does not have to rediscover it. Full detail (including why no
earlier number in this research is invalidated by it) is in the P3 section
above, "Guard-suite gap".

## What would move (Task 8)

Nothing ships from this effort. `git diff main -- modern_di/` and `git diff
main -- docs/` are both empty on `research/clean-fast-resolve`, and
`docs/introduction/performance.md` was not touched. This section records
what the published comparative table (`docs/introduction/performance.md`,
generated by `just bench-report`) *would* show *if* a subset of the
candidates above shipped — a hypothetical, not a change in flight. Full raw
tables, the rivals'-absolutes drift check, and the cherry-pick verification
live in `.superpowers/sdd/2026-07-28-clean-fast-resolve-research/task-8-report.md`.

**Which candidates, and why only these two — and why neither is cleared to
ship.** The brief's own instruction ("cherry-pick the `do-first` or
`needs-decision` candidates") would literally include P2 and P3 alongside P1.
The controller ruled narrower: **combine only P1 (`spike/p1-closed-check`
`344ff50`) and P2 (`spike/p2-override-compile` `c84912a`)** — the two
candidates that measure as plausible performance wins. **Neither is
unblocked.** P1's own bucket, quoted verbatim from this report's P1 section
above (not paraphrased as `do-first`, a label never attached to P1 anywhere
in this document): "real, small, node-count-scaling perf win, gated on an
unresolved behavior-delta decision — not a free lunch, and **not to be
shipped until the maintainer rules** on whether the silent-no-warning /
stays-closed outcome for a creator that closes its own resolving container
mid-flight is acceptable." P2's bucket is `needs-decision` on three open
calls named in the P2 section above: the override-race remedy, the
provider-backed-vs-context-backed override-semantics split, and whether the
target workload's resolves-per-override ratio clears the measured ~30-resolve
break-even. **P3 is excluded on purpose, not merely left for later**: it is a
*cost* (+9-13% on construction-heavy scenarios, 3-4x its own budget), filed
`needs-decision` only because the maintainer ruling on it is open, not
because its numbers are ship-plausible; folding it in would drag every
construction-heavy cell down and answer a question nobody asked. **P4 is
excluded** as a straightforward `skip` (~1.35x against the ~2x bar this
repo holds copy-adding changes to). **Nothing below should be read as "P1+P2
are cleared to ship"** — it is a hypothetical conditioned on two rulings that
have not been made, not a verdict that they should be, and not "all
surviving candidates."

**Cherry-pick, verified rather than assumed clean.** `git checkout -b
spike/finalists main`, then `git cherry-pick 344ff50 c84912a` in that order.
Contrary to what both the brief and the controller's note anticipated, this
produced **no textual conflict** — git auto-merged
`modern_di/resolver_compiler.py` cleanly, because P1's and P2's deleted
blocks (the closed-check and the override front-guard) sit in the same
closures but never overlap line-for-line. A clean auto-merge is not proof of
a clean semantic result, so the combined file was checked directly: `grep -n
"target.closed\|has_overrides\|fetch_override" modern_di/resolver_compiler.py`
returns exactly one hit, `target.closed` inside `_navigate` (P1's hoisted
check, the only place it should remain) — no override guard anywhere. `just
test` passes 452/452, the same count as unmodified `main`; `just test-ci`
(run beyond the brief's own gate, for stronger assurance) passes at 100%
line coverage. **Reading:** P1 and P2 do not conflict, textually or
semantically — they edit disjoint regions within shared closures and compose
without hand-reconciliation. This is the opposite of the risk the
controller's note flagged; nothing here suggests the two "cannot ship
independently."

**Rivals'-absolutes sanity check.** A three-run sequence (`main` → `spike/finalists`
→ `main` again) was used instead of trusting a single `main`-vs-candidate
pair. The four rivals' own absolutes did shift 1-3.5% between the first
`main` run and `spike/finalists` — on its face the "machine drifted, re-run"
case — but the third run (`main` again, identical code to the first) showed
**the same 1-3.5% shift**, confirming the drift is session-level
(ambient/thermal) and not attributable to the branch. The mechanism is a
first-run cold-start effect saturating, not continued drift: the rivals step
up once from run 1 to run 2, then plateau or fall back on run 3 (C2 wireup:
73.5 ns → 76.0 ns → 75.1 ns) — `main`'s first run is the odd one out, not the
stable reference point.

modern-di's own no-code drift, checked the same way, is +0.05% to +1.73% —
smaller than the rivals' +0.95% to +3.52%, not "the same band" as an earlier
draft of this section said. That gap matters because the published cells
are **ratios**, and whatever part of the rivals' drift modern-di does not
share flows uncancelled into every ratio cell — so the comparison has to be
validated at the ratio level, not just on the two sides' absolutes
separately. Recomputing all twenty published ratio cells the same way
(`main #1` vs `main #2`, no code change) gives the actual no-code drift per
cell, ranging from near-zero to about 3%; every claimed move below is read
against that figure rather than a single blanket band. The published cells
themselves still use the first `main` run as baseline (matching Task 8's
Step 2 exactly) — the third run exists only to validate the comparison.

**One estimator throughout, to avoid mixing them (mirrored into this report,
Task 9).** Every ratio figure below and in the drift table is computed the same
way: for each of the 5 runs in a branch's invocation, the ratio is `modern-di
median / rival median` *for that run*, and the 5 per-run ratios are then
averaged. That single method is applied identically to `main #1`,
`spike/finalists`, and `main #2`. The first draft of this section mixed
estimators — comparing a rounded, published *median-of-medians* figure against
a *mean-of-medians* drift figure — which is exactly the kind of arithmetic that
manufactures a move out of nothing. A move is called "real" here only when its
magnitude both exceeds roughly 3% and exceeds that cell's own no-code drift by
a wide margin; the move-to-drift ratio itself is the deciding evidence, not a
fixed cutoff, because the drift varies per cell from near-zero to over 3%.

**Reconciling the published `±` figures with the drift band, since they look
contradictory otherwise (mirrored into this report, Task 9).** The comparative
tables carry per-cell `±` figures (e.g. `C2 warm singleton 138 ns ±5.0%`) that
are *larger* than most of the drift figures used here to judge a move — which
reads like a contradiction, and is not one. They are two different quantities:
the `±` is the run-to-run **spread within one branch's own 5 repetitions** —
raw noise, unaveraged. The drift figures are the **shift in the average**
between two independent 5-run invocations of unchanged code, and averaging
suppresses most of that per-run noise, which is why they come out mostly under
3%. Nothing here contradicts the published `±` values; a large `±` alongside a
small drift is the expected shape, not a warning sign.

**Ratio-level no-code drift (`main #2` vs `main #1`), all twenty published
cells.** This is the evidence every "clears its own drift by Nx" claim below
rests on, reproduced here rather than left in a working file:

| Cell | main #1 | finalists | main #2 | move (fin vs m1) | drift (m2 vs m1) | \|move\|/\|drift\| |
|---|---|---|---|---|---|---|
| C1 by-ref vs dependency-injector | 0.770 | 0.711 | 0.762 | -7.62% | -0.94% | 8.1x |
| C1 by-ref vs that-depends | 0.900 | 0.835 | 0.900 | -7.22% | -0.05% | 156x |
| C2 by-ref vs dependency-injector | 2.917 | 2.716 | 2.956 | -6.89% | +1.32% | 5.2x |
| C2 by-ref vs that-depends | 2.131 | 1.997 | 2.133 | -6.30% | +0.09% | 69x |
| C3 by-ref vs dependency-injector | 0.529 | 0.504 | 0.528 | -4.74% | -0.17% | 27.7x |
| C3 by-ref vs that-depends | 0.720 | 0.668 | 0.718 | -7.27% | -0.39% | 18.8x |
| C1 by-type vs dishka | 1.353 | 1.265 | 1.334 | -6.55% | -1.44% | 4.6x |
| C1 by-type vs wireup | 1.513 | 1.409 | 1.504 | -6.87% | -0.56% | 12.2x |
| C2 by-type vs dishka | 1.078 | 1.003 | 1.046 | -6.96% | -3.00% | **2.3x** |
| C2 by-type vs wireup | 2.414 | 2.241 | 2.360 | -7.15% | -2.23% | 3.2x |
| C3 by-type vs dishka | 1.812 | 1.689 | 1.813 | -6.77% | +0.08% | 88.4x |
| C3 by-type vs wireup | 1.250 | 1.176 | 1.258 | -5.96% | +0.58% | 10.3x |
| C4 vs dependency-injector | 0.0190 | 0.0190 | 0.0190 | -0.16% | +0.26% | 0.6x |
| C4 vs that-depends | 0.1988 | 0.1994 | 0.2026 | +0.34% | +1.93% | 0.2x |
| C4 vs dishka | 1.253 | 1.242 | 1.251 | -0.86% | -0.18% | 4.8x |
| C4 vs wireup | 0.1220 | 0.1222 | 0.1226 | +0.16% | +0.45% | 0.4x |
| C6 vs dependency-injector | 0.590 | 0.567 | 0.580 | -3.83% | -1.64% | **2.3x** |
| C6 vs that-depends | 0.640 | 0.627 | 0.644 | -2.09% | +0.62% | **3.4x** |
| C6 vs dishka | 1.635 | 1.604 | 1.645 | -1.87% | +0.66% | **2.8x** |
| C6 vs wireup | 1.426 | 1.377 | 1.390 | -3.43% | -2.48% | **1.4x** |

**By-reference resolution**

| Scenario | modern-di (main → finalists) | vs dependency-injector | vs that-depends |
|---|---|---|---|
| C1 transient | 274 ns → 257 ns | 0.77 → **0.72** | 0.91 → **0.84** |
| C2 warm singleton | 138 ns → 133 ns | 2.95 → 2.74 | 2.15 → 2.00 |
| C3 deep chain (6) | 750 ns → 699 ns | 0.53 → **0.51** | 0.73 → **0.67** |

**By-type resolution**

| Scenario | modern-di (main → finalists) | vs dishka | vs wireup |
|---|---|---|---|
| C1 transient | 318 ns → 301 ns | 1.35 → 1.27 | 1.51 → 1.41 |
| C2 warm singleton | 177 ns → 170 ns | 1.08 → **1.00** | 2.42 → 2.23 |
| C3 deep chain (6) | 785 ns → 746 ns | 1.81 → 1.68 | 1.25 → 1.17 |

**Request lifecycle / per-request context**

| Scenario | modern-di (main → finalists) | vs dependency-injector | vs that-depends | vs dishka | vs wireup |
|---|---|---|---|---|---|
| C4 request lifecycle | 1.88 µs → 1.87 µs | 0.02 → 0.02 | 0.20 → 0.20 | 1.25 → 1.24 | 0.12 → 0.12 |
| C6 context | 1.38 µs → 1.35 µs | 0.59 → 0.57 | 0.65 → 0.64 | 1.63 → 1.60 | 1.42 → 1.38 |

**One-line reading, per row — read against each cell's own no-code drift, not
a blanket band.** By-reference and by-type C1 and C3 clear their own drift by
4.6x-156x (a full order of magnitude or more in nine of the ten cells) — real
without qualification, every ratio narrowing or widening further in
modern-di's direction. By-type C2 clears its own drift by a narrower 2.3-3.2x
— still real, but the weakest-margin cells in the "real" group. The single
qualitative crossing: **by-type C2 vs dishka goes from 1.05-1.08 (depending
which `main` run is used as baseline) to 1.00** — P1+P2 bring modern-di's
warm-singleton by-type resolve to effective parity with dishka. (An earlier
draft quoted this as "`main` trails by ~8%," which is `main #1` alone; the
`main #2` recheck measures the same ratio at 1.046 — about a third of that
gap was itself session drift, and the drift-corrected move is closer to
-4-5%. The parity conclusion is unchanged; only the starting-point quote is
corrected.)

C4 is flat: all four ratio cells move under 1%, and three of the four move by
*less* than their own no-code drift — expected, since C4 is dominated by
event-loop entry and async finalizer wall time, not the synchronous
resolve-closure cost P1/P2 touch.

**C6 is not separable from ambient drift — not a move.** All four C6 ratio
cells clear their own drift by only 1.4x-3.4x, well below the 4.6x floor
every C1/C3 cell clears. All four moves are negative; the drift figures are
`vs dependency-injector` **-1.64%**, `vs that-depends` **+0.62%**, `vs dishka`
**+0.66%**, `vs wireup` **-2.48%** — so two share the move's sign (a large
fraction of the apparent move reproducing on unchanged code), and **two flip
sign relative to it** (`vs that-depends` and `vs dishka`), not the one an
earlier draft of this paragraph claimed. (Correction, Task 9, from
recomputation of the ratio-drift table above. The error was conservative — it
understated how unstable these cells are between two runs of identical code —
but it was still wrong.) This cannot be resolved as real or noise from one candidate
observation. The mechanism named for it (`ContextGroup`'s handler node mixes
a live, uninlined `fetch_override` call that P2's compile-time check does not
reach, per the P2 section's finding 3) is retained only as a plausible reason
any true effect here would be small and hard to separate at this sample
size — not as evidence the move is real.

**One caveat outside the published table.** C5 (cold build + first resolve,
not published — `benchmarks/README.md`: "C5 is not published on the page")
moved **against** the candidate: +4.96% on `spike/finalists` vs the first
`main` run, against only +1.92% of ambient drift on the same metric in the
recheck — so part of the rise is real. The likely mechanism is P2's added
construction-time work in `Container.__init__`/`ProvidersRegistry.__init__`
(`container.py +3 -1`, `providers_registry.py +14 -1`), which C5's cold-build
path runs on every timed call; P2's per-provider compile-time override check
alone (6 calls per cold build, each tens of ns) explains at most 10-30% of
the residual, not the bulk of it. This affects no published cell, but "P1+P2
have no downside anywhere" would overstate the finding.
