---
summary: `_compile_cached_factory`'s cold-miss builders have no sensitive guard scenario — G8 is all-transient and never reaches them, and G15's incidental coverage dilutes a single builder ~50x, so a regression there could pass unnoticed.
---

# No sensitive guard benchmark for a cached-provider cold miss

`_compile_cached_factory`'s cold-miss builders (`build_cold` / `create_cold`)
have no guard scenario that would show a regression in them.

## Why it is open

The dedicated cold scenario, **G8** (`benchmarks/test_guard_cold.py`), builds from
a local **all-transient** `ChainGroup` — no provider sets `cache=True` — so it
never reaches those builders at all. It times construction plus a six-node
transient compile.

The only committed coverage is incidental, inside **G15**
(`benchmarks/test_guard_concurrency.py`), whose `n_threads=1` case does build a
fresh container per round over 50 `cache=True` providers and therefore does time
them.

So this is a **sensitivity** gap, not a coverage gap — which is what makes it easy
to miss. Three things stack:

1. G15 batches 50 cold misses into one timed call, diluting a single builder's
   cost roughly 50x.
2. `benchmarks/README.md` explicitly instructs readers to take G15 as a
   thread-count *trend* rather than as absolutes.
3. Guard-bench is non-gating — `fail-on-alert: false` and
   `alert-threshold: "150%"` in
   [`benchmarks.yml`](../../.github/workflows/benchmarks.yml).

A regression confined to the cold-miss builders would have to survive 50x dilution
*and* exceed 150% in a job that cannot fail the build.

Closing it is one small scenario: a `cache=True` sibling of G8 — build a fresh
root, resolve one cached provider, time the whole thing. That also gives the cold
path the same before/after instrument the warm path already has in G2.

Found while isolating the cached-builder half of a body-merge candidate during the
2026-07-28 resolve research; that work measured the half with a throwaway `g2_cold`
probe in a git-ignored harness, which closed nothing in the repo. (An earlier
revision of that research overstated this as "no benchmark at all" — G15 disproves
that; the gap is sensitivity, as described above.)

## Revisit trigger

The next change that touches `_compile_cached_factory`'s cold-miss builders — add
the scenario **first**, so the change has a baseline to move against. Otherwise
whenever the guard suite is next extended.
