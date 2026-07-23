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

Sources per row: `../modern-di-<name>/README.md`, `docs/integrations/<name>.md` (this
repo), `../modern-di-<name>/modern_di_<name>/main.py`,
`../modern-di-<name>/modern_di_<name>/__init__.py`. D5 is scored in Task 3.

| Integration | D1 setup | D2 example | D3 lifespan | D4 steps(L) | D5 | D6 readme |
|---|---|---|---|---|---|---|
| aiogram | 2 (1 action; `../modern-di-aiogram/modern_di_aiogram/main.py:41-49`) | 1 (`../modern-di-aiogram/README.md:34-63`) | 2 (`../modern-di-aiogram/modern_di_aiogram/main.py:41-49`; no documented root-open caveat) | 1 (L=8; `../modern-di-aiogram/README.md:34-63`) | ? | 1 (missing canonical-example line; `../modern-di-aiogram/README.md:22-24`) |
| aiohttp | 2 (1 action; `../modern-di-aiohttp/modern_di_aiohttp/main.py:76-82`) | 1 (`../modern-di-aiohttp/README.md:34-69`) | 2 (`../modern-di-aiohttp/modern_di_aiohttp/main.py:76-82`; no documented root-open caveat) | 1 (L=8; `../modern-di-aiohttp/README.md:34-69`) | ? | 1 (missing canonical-example line; `../modern-di-aiohttp/README.md:22-24`) |
| arq | 2 (1 action; `../modern-di-arq/modern_di_arq/main.py:84-117`) | 1 (`../modern-di-arq/README.md:34-75`) | 2 (`../modern-di-arq/modern_di_arq/main.py:84-117`; no documented root-open caveat) | 1 (L=8; `../modern-di-arq/README.md:34-75`) | ? | 1 (missing canonical-example line; `../modern-di-arq/README.md:22-24`) |
| celery | 2 (1 action; `../modern-di-celery/modern_di_celery/main.py:15-41`) | 1 (`../modern-di-celery/README.md:34-71`) | 1 (root owned by `setup_di`, main.py:15-41; per-task child owned by `@inject`/`DITask`, not `setup_di`, main.py:54-88; documented `task_always_eager` root-open caveat, `../modern-di-celery/README.md:73` and `docs/integrations/celery.md:64,140-175`) | 1 (L=8; `../modern-di-celery/README.md:34-71`) | ? | 1 (missing canonical-example line; `../modern-di-celery/README.md:22-24`) |
| fastapi | 2 (1 action; `../modern-di-fastapi/modern_di_fastapi/main.py:47-51`) | 2 (`../modern-di-fastapi/README.md:24`) | 1 (`../modern-di-fastapi/modern_di_fastapi/main.py:47-60` owns both sides; documented mounted-sub-app/disabled-lifespan caveat, `docs/integrations/fastapi.md:66-73`) | 2 (L=7; `../modern-di-fastapi/README.md:36-67`) | ? | 2 (all elements present and ordered; `../modern-di-fastapi/README.md:1-91`) |
| faststream | 2 (1 action; `../modern-di-faststream/modern_di_faststream/main.py:60-78`) | 1 (`../modern-di-faststream/README.md:34-67`) | 1 (`../modern-di-faststream/modern_di_faststream/main.py:60-78` owns both sides; documented `TestBroker`/`TestApp` caveat, `docs/integrations/faststream.md:125-131`) | 2 (L=7; `../modern-di-faststream/README.md:34-67`) | ? | 1 (missing canonical-example line; `../modern-di-faststream/README.md:22-24`) |
| flask | 1 (2 actions: `setup_di` + manual `container.open()`; `../modern-di-flask/modern_di_flask/main.py:28-43`, `../modern-di-flask/README.md:63-65`) | 1 (`../modern-di-flask/README.md:34-66`) | 1 (`setup_di` owns only the per-request child, `main.py:28-43`; root teardown is manual, `docs/integrations/flask.md:123-127`) | 1 (L=9; `../modern-di-flask/README.md:34-66`) | ? | 1 (missing canonical-example line; `../modern-di-flask/README.md:22-24`) |
| grpc | 1 (2 actions: manual `container.open()`/`close_sync()` + `DIInterceptor` registration; `../modern-di-grpc/README.md:75-84`) | 1 (`../modern-di-grpc/README.md:34-85`) | 1 (`DIInterceptor` owns only the per-RPC child, `../modern-di-grpc/modern_di_grpc/main.py:137-156`; root lifecycle is manual, `../modern-di-grpc/README.md:87` and `docs/integrations/grpc.md:153-162`) | 0 (L=10; `../modern-di-grpc/README.md:34-85`) | ? | 1 (missing canonical-example line; `../modern-di-grpc/README.md:22-24`) |
| litestar | 2 (1 action; `../modern-di-litestar/modern_di_litestar/main.py:64-70`) | 2 (`../modern-di-litestar/README.md:24`) | 2 (`../modern-di-litestar/modern_di_litestar/main.py:64-70` owns both sides; no documented root-open caveat) | 2 (L=7; `../modern-di-litestar/README.md:34-97`) | ? | 2 (all elements present and ordered; `../modern-di-litestar/README.md:1-154`) |
| starlette | 2 (1 action; `../modern-di-starlette/modern_di_starlette/main.py:73-78`) | 1 (`../modern-di-starlette/README.md:34-72`) | 1 (`../modern-di-starlette/modern_di_starlette/main.py:73-78` owns both sides; documented mounted-sub-app/disabled-lifespan caveat, `docs/integrations/starlette.md:74-81`) | 1 (L=8; `../modern-di-starlette/README.md:34-72`) | ? | 1 (missing canonical-example line; `../modern-di-starlette/README.md:22-24`) |
| taskiq | 2 (1 action; `../modern-di-taskiq/modern_di_taskiq/main.py:19-31`) | 1 (`../modern-di-taskiq/README.md:34-70`) | 1 (`../modern-di-taskiq/modern_di_taskiq/main.py:19-31` owns both sides; documented `run_receiver_task(run_startup=False)` caveat, `docs/integrations/taskiq.md:67-72`) | 2 (L=7; `../modern-di-taskiq/README.md:34-70`) | ? | 1 (missing canonical-example line; `../modern-di-taskiq/README.md:22-24`) |
| typer | 1 (2 actions: `setup_di` + manual `with container:`; `../modern-di-typer/modern_di_typer/main.py:18-24`, `../modern-di-typer/README.md:59-61`) | 1 (`../modern-di-typer/README.md:32-62`) | 0 (`setup_di` owns neither side: root is opened manually via `with container:`, `README.md:59-61`; the per-command child is built inside `@inject`'s wrapper, not by `setup_di`, `../modern-di-typer/modern_di_typer/main.py:18-24,31-34,69-83`) | 1 (L=9; `../modern-di-typer/README.md:32-62`) | ? | 1 (missing canonical-example line; `../modern-di-typer/README.md:22-24`) |

## §3 Per-integration notes

<!-- filled in Task 3 -->

## §4 Prioritized backlog

<!-- filled in Task 4 -->

## §5 Cross-cutting findings

<!-- filled in Task 4 -->

## Appendix: modern-di-pytest (not scored)

<!-- filled in Task 5 -->
