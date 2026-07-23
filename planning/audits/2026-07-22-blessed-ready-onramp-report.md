# Blessed-ready on-ramp audit — 2026-07-22

This is a read-only, source-and-docs read-through audit of the 12 framework integrations
against the A2 blessed-ready criterion named in the
[2026-06-18 adoption strategy report](2026-06-18-adoption-strategy-report.md) but never
produced; no apps are run, the sub-5-min onboarding claim is measured by a step-count
proxy rather than a stopwatch, and every score cites a `file:line` or README section per
the [spec](../changes/2026-07-22.01-blessed-ready-onramp-audit.md).

## §1 Rubric

Each subject is scored **0 / 1 / 2** per dimension against the bars below. Bars are
written so the score is determined by a countable fact, not a judgment call.

1. **One-call setup** — count the distinct DI wiring actions the user performs to
   activate the integration (register the container + open per-request scope + bind
   lifecycle), where an action ∈ {call `setup_di`; add a middleware/hook; register a
   plugin/extension; open/close the root by hand}. **2:** one action (a single
   `setup_di(app, container)` does all of it). **1:** exactly two actions. **0:** three
   or more, or the user hand-assembles middleware.
2. **Canonical example present + linked** — **2:** README links a dedicated, runnable
   starter as `Usage example: <repo>` (today: FastAPI, Litestar). **1:** the README's
   inline Usage block is complete and copy-paste-runnable but there is no dedicated
   starter (generic "browse templates" footer only). **0:** no complete runnable
   example — only fragmentary snippets.
3. **Lifespan handled for the user** — **2:** `setup_di` owns *both* root open/close and
   per-request (child-scope) open/close; the user writes no lifecycle code and there is
   no documented deployment context where the root fails to open. **1:** `setup_di`
   owns one side but the user must own the other, *or* there is a documented deployment
   caveat where the root's open hook does not fire (the root-open traps: mounted ASGI
   sub-app / disabled lifespan, taskiq `run_startup=False`, FastStream `TestBroker`,
   Celery non-prefork pools). **0:** the user must wire both root and child lifecycle by
   hand.
4. **Steps-to-first-dependency** (sub-5-min proxy) — count **L**, the DI-specific lines
   in a *minimal single-dependency* quickstart: imports of modern-di/integration
   symbols, the `Group` + its one provider, the `Container` construction, `setup_di`,
   the per-handler marker/decorator, and any manual lifecycle hook — excluding the
   framework app object, the business class body, and the handler body. **2:** L ≤ 7.
   **1:** 8 ≤ L ≤ 9. **0:** L ≥ 10. (Calibration: a decorator-free integration lands ≈7;
   `@inject` adds one line; a manual lifecycle hook adds one or two more.)
5. **`@inject` presence + avoidability** — **2:** no DI decorator at the handler
   (fastapi, litestar, faststream, taskiq). **1:** `@inject` required *and* inherent —
   the framework exposes no parameter-injection seam, so no adapter could remove it
   (e.g. Flask, Typer). **0:** `@inject` required *but avoidable* — the framework
   offers a seam the adapter does not yet use. Deciding 1 vs 0 per integration is the
   substance this dimension contributes to the downstream `@inject`-asymmetry thread.
6. **README consistency** — against the shared structure: brand lockup + badge block,
   one-line intro + `Full guide` link + canonical-example line, `## Installation`,
   `## Usage` (with the lifecycle/ordering note where it applies), footer. **2:** all
   elements present and in order. **1:** exactly one element missing or out of order.
   **0:** two or more missing, or a divergent format.

**Verdict rule (locked).** A subject is **blessed-ready** iff it scores **2 on
dimensions 1, 2, and 3** (the newcomer-facing essentials — one-call setup, canonical
example, lifecycle handled) **and has no 0 in any dimension**. A dimension-5 score of
**1** (inherent `@inject`) does *not* block the verdict — only dimension-5 = 0
(avoidable-but-not-avoided) does. Everything else is **not yet**, and §4 ranks its
shortfall.

The per-dimension score drives the verdict and the ranking; the §3 prose carries the
finding. The per-subject sum (0–12) is reported only as a coarse sort key, not claimed
as a precise measure.

## §2 Scorecard

<!-- filled in Task 2 -->

## §3 Per-integration notes

<!-- filled in Task 3 -->

## §4 Prioritized backlog

<!-- filled in Task 4 -->

## §5 Cross-cutting findings

<!-- filled in Task 4 -->

## Appendix: modern-di-pytest (not scored)

<!-- filled in Task 5 -->
