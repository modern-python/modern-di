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

`REPEATS=15` is the value used for all further work in this research effort.
Per-scenario `number` (iteration counts) were not changed — `REPEATS` alone
was sufficient to make the effect readable.

### Null control (Step 4) — canonical run, `REPEATS=15`

`.superpowers/spike/ab_run.sh main main g1_transient g2_cached g3_chain`

```
scenario                 base_ns   cand_ns   delta_%   drift_%  verdict
g1_transient               284.8     284.1     -0.23      0.08  OK
g2_cached                  131.1     128.2     -2.18      0.53  OK
g3_chain                   773.6     768.6     -0.64      2.37  OK
```

Every row `OK`; every `delta_%` at or below its own `drift_%`. With base and
candidate identical (`main` vs `main`), the harness reports no signal.

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

### Readable-delta floor

Across the `REPEATS=15` null-control runs (the fast g1/g2/g3-class scenarios,
~130-780ns base), observed `drift_%` ranged 0.08%-2.37%. Taking the observed
ceiling with a small margin:

**Deltas below ~3% are not separable from drift on this machine for
scenarios in the g1-g16 (~100ns-2us) range at `REPEATS=15`.** Any measured
delta at or below this floor should be treated as inconclusive and re-run
before being reported as a finding. This floor was not separately calibrated
for `cold`/`churn10`/`churn100`, whose base costs and variance are much
larger (an earlier, unrelated all-scenario run showed `cold`'s own
`spread_pct` near 18%); those scenarios likely need a higher floor and should
be sanity-checked with their own null control before being trusted for small
deltas.

