---
summary: D1 (one-call setup) and D4 (quickstart length) sub-2 scores are arithmetic consequences of the already-inherent @inject (D5) and caller-owned root lifecycle (D3) — no independent quickstart or setup fix; the audit's item-5 one-line trim does not hold. Post-rollout blessed-ready count is 4 (the ceiling under the inherent rulings).
---

# D1/D4 sub-2 scores are derived — no independent fix

**Decision:** The D1 and D4 scores below 2 in the 2026-07-22 blessed-ready
on-ramp audit are arithmetic consequences of two facts already ruled inherent — the `@inject`
requirement ([D5](2026-07-25-inject-asymmetry-inherent.md)) and the caller-owned
root lifecycle ([D3](2026-07-25-d3-root-lifecycle-inherent.md)) — not independent
gaps. No quickstart or `setup_di` changes; the audit's §4 item-5 "trim one line"
does not hold.

## Context

D1 scores one-call setup (distinct wiring actions); D4 scores steps-to-first-
dependency (`L`, the DI-specific lines in a minimal single-dependency quickstart,
2 = `L` ≤ 7). The audit's §4 backlog carried D4 items (5, and the D4 halves of 8,
9) and D1 items (7, 8, 9) as candidate "quickstart trims." This checks whether any
is an independent fix once D3 and D5 are ruled inherent.

## Decision & rationale

**D1 < 2 is D3, restated.** Only flask, grpc, typer score D1=1, and in each the
second action is the manual root `open()` — the exact caller-owned-root fact ruled
inherent in the D3 decision. The audit itself notes flask's "D1=1 and D3=1 share
one root cause." No independent D1 fix exists.

**D4 < 2 is D5 + D3, by line count.** The decorator-free floor is `L`=7 (two
imports, a `Group` + one provider + its dependency, `Container(...)`, `setup_di`).
Verified against the merged examples:

- **aiogram, aiohttp, arq** — `L`=8 = the floor **+ the `@inject` line** (D5,
  inherent). The audit's item 5 ("trim one line, D5 not part of it") is wrong: the
  only line over 7 *is* `@inject`.
- **flask, typer** — `L`=9 = floor + `@inject` + the manual root `open()`/`with`
  (D3, inherent).
- **grpc** — `L`=10 = floor + `@inject` + manual `open()` + `close_sync()` (D3,
  inherent); the lone D4=0.

Nothing is trimmable without deleting an inherent element. A minimal
single-dependency example needs both providers (a service *and* the thing it
depends on) to demonstrate DI at all, so the floor itself cannot drop.

**The scores are also mostly moot.** The verdict rule is D1=D2=D3=2 and no `0`;
**D4=1 and D5=1 never block.** So once the canonical-example rollout fixed D2/D6,
the D4=1 rows are not held back by D4 at all — only grpc's D4=0 is a dimension-
zero, and grpc is already blocked by its inherent D1/D3.

**Corrected blessed-ready count: 4.** Post-rollout, litestar plus **aiogram,
aiohttp, arq** clear the verdict (D1=D2=D3=2, no zero; their D4=1/D5=1 do not
block) — up from 1 at audit time. That is the **ceiling** under the inherent
rulings: the other eight are each gated by a framework-inherent **D3** lifecycle
score (or, for flask/grpc/typer, D1 too), every one with a revisit trigger in the
D3/D5 records. No integration reaches blessed-ready by a quickstart edit.

**Consistency.** Same conclusion as the D3, D5, and
[exec](2026-07-19-exec-hot-path-declined.md) records: a sub-2 score reflecting a
framework limitation, not a modern-di gap, is documented, not engineered away.

## Revisit trigger

Whichever underlying record reopens: if `@inject` (D5) or the caller-owned root
lifecycle (D3) becomes avoidable for an integration, its D1/D4 improve for free.
No independent D1/D4 trigger.
