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

| Integration | D1 setup | D2 example | D3 lifespan | D4 steps(L) | D5 | D6 readme | Verdict | Σ |
|---|---|---|---|---|---|---|---|---|
| aiogram | 2 (1 action; `../modern-di-aiogram/modern_di_aiogram/main.py:41-49`) | 1 (`../modern-di-aiogram/README.md:34-63`) | 2 (`../modern-di-aiogram/modern_di_aiogram/main.py:41-49`; no documented root-open caveat) | 1 (L=8; `../modern-di-aiogram/README.md:34-63`) | 1 (@inject required, inherent — aiogram's name-based contextual-data injection can't evaluate `FromDI` marker defaults, so no per-param provider seam; `docs/integrations/aiogram.md:3`, `../modern-di-aiogram/modern_di_aiogram/main.py:62-90`) | 1 (missing canonical-example line; `../modern-di-aiogram/README.md:22-24`) | not yet | 8 |
| aiohttp | 2 (1 action; `../modern-di-aiohttp/modern_di_aiohttp/main.py:76-82`) | 1 (`../modern-di-aiohttp/README.md:34-69`) | 2 (`../modern-di-aiohttp/modern_di_aiohttp/main.py:76-82`; no documented root-open caveat) | 1 (L=8; `../modern-di-aiohttp/README.md:34-69`) | 1 (@inject required, inherent — no DI seam, handler is `async def handler(request)`; `docs/integrations/aiohttp.md:3`, `../modern-di-aiohttp/modern_di_aiohttp/main.py:88-96`) | 1 (missing canonical-example line; `../modern-di-aiohttp/README.md:22-24`) | not yet | 8 |
| arq | 2 (1 action; `../modern-di-arq/modern_di_arq/main.py:84-117`) | 1 (`../modern-di-arq/README.md:34-75`) | 2 (`../modern-di-arq/modern_di_arq/main.py:84-117`; no documented root-open caveat) | 1 (L=8; `../modern-di-arq/README.md:34-75`) | 1 (@inject required, inherent — arq calls the task as `coroutine(ctx, *args, **kwargs)`, no per-param provider seam; `../modern-di-arq/modern_di_arq/main.py:134-135,131-188`) | 1 (missing canonical-example line; `../modern-di-arq/README.md:22-24`) | not yet | 8 |
| celery | 2 (1 action; `../modern-di-celery/modern_di_celery/main.py:15-41`) | 1 (`../modern-di-celery/README.md:34-71`) | 1 (root owned by `setup_di`, main.py:15-41; per-task child owned by `@inject`/`DITask`, not `setup_di`, main.py:54-88; documented `task_always_eager` root-open caveat, `../modern-di-celery/README.md:73` and `docs/integrations/celery.md:64,140-175`) | 1 (L=8; `../modern-di-celery/README.md:34-71`) | 1 (@inject required, inherent — task is a plain callable invoked with its own args, no per-param provider seam; `docs/integrations/celery.md:138`, `../modern-di-celery/modern_di_celery/main.py:54-88`) | 1 (missing canonical-example line; `../modern-di-celery/README.md:22-24`) | not yet | 7 |
| fastapi | 2 (1 action; `../modern-di-fastapi/modern_di_fastapi/main.py:47-51`) | 2 (`../modern-di-fastapi/README.md:24`) | 1 (`../modern-di-fastapi/modern_di_fastapi/main.py:47-60` owns both sides; documented mounted-sub-app/disabled-lifespan caveat, `docs/integrations/fastapi.md:66-73`) | 2 (L=7; `../modern-di-fastapi/README.md:36-67`) | 2 (no handler decorator — `FromDI` is a `fastapi.Depends` parameter default; `../modern-di-fastapi/modern_di_fastapi/main.py:73-76`) | 2 (all elements present and ordered; `../modern-di-fastapi/README.md:1-91`) | not yet | 11 |
| faststream | 2 (1 action; `../modern-di-faststream/modern_di_faststream/main.py:60-78`) | 1 (`../modern-di-faststream/README.md:34-67`) | 1 (`../modern-di-faststream/modern_di_faststream/main.py:60-78` owns both sides; documented `TestBroker`/`TestApp` caveat, `docs/integrations/faststream.md:125-131`) | 2 (L=7; `../modern-di-faststream/README.md:34-67`) | 2 (no handler decorator — `FromDI` is a `faststream.Depends` parameter default; `../modern-di-faststream/modern_di_faststream/main.py:90-96`) | 1 (missing canonical-example line; `../modern-di-faststream/README.md:22-24`) | not yet | 9 |
| flask | 1 (2 actions: `setup_di` + manual `container.open()`; `../modern-di-flask/modern_di_flask/main.py:28-43`, `../modern-di-flask/README.md:63-65`) | 1 (`../modern-di-flask/README.md:34-66`) | 1 (`setup_di` owns only the per-request child, `main.py:28-43`; root teardown is manual, `docs/integrations/flask.md:123-127`) | 1 (L=9; `../modern-di-flask/README.md:34-66`) | 1 (@inject required, inherent — no DI seam / no `Depends`, view is a plain callable; `docs/integrations/flask.md:3-4`, `../modern-di-flask/modern_di_flask/main.py:61-74`) | 1 (missing canonical-example line; `../modern-di-flask/README.md:22-24`) | not yet | 6 |
| grpc | 1 (2 actions: manual `container.open()`/`close_sync()` + `DIInterceptor` registration; `../modern-di-grpc/README.md:75-84`) | 1 (`../modern-di-grpc/README.md:34-85`) | 1 (`DIInterceptor` owns only the per-RPC child, `../modern-di-grpc/modern_di_grpc/main.py:137-156`; root lifecycle is manual, `../modern-di-grpc/README.md:87` and `docs/integrations/grpc.md:153-162`) | 0 (L=10; `../modern-di-grpc/README.md:34-85`) | 1 (@inject required, inherent — gRPC always calls a servicer method as fixed `(request, context)`, no per-param provider seam; `docs/integrations/grpc.md:177-178`, `../modern-di-grpc/modern_di_grpc/main.py:45-80`) | 1 (missing canonical-example line; `../modern-di-grpc/README.md:22-24`) | not yet | 5 |
| litestar | 2 (1 action; `../modern-di-litestar/modern_di_litestar/main.py:64-70`) | 2 (`../modern-di-litestar/README.md:24`) | 2 (`../modern-di-litestar/modern_di_litestar/main.py:64-70` owns both sides; no documented root-open caveat) | 2 (L=7; `../modern-di-litestar/README.md:34-97`) | 2 (no handler decorator — `FromDI` is a Litestar `Provide` dependency; `../modern-di-litestar/modern_di_litestar/main.py:92-93`) | 2 (all elements present and ordered; `../modern-di-litestar/README.md:1-154`) | blessed-ready | 12 |
| starlette | 2 (1 action; `../modern-di-starlette/modern_di_starlette/main.py:73-78`) | 1 (`../modern-di-starlette/README.md:34-72`) | 1 (`../modern-di-starlette/modern_di_starlette/main.py:73-78` owns both sides; documented mounted-sub-app/disabled-lifespan caveat, `docs/integrations/starlette.md:74-81`) | 1 (L=8; `../modern-di-starlette/README.md:34-72`) | 1 (@inject required, inherent — no DI seam / no `Depends`, endpoint is a plain ASGI callable; `docs/integrations/starlette.md:3-4`, `../modern-di-starlette/modern_di_starlette/main.py:84-100`) | 1 (missing canonical-example line; `../modern-di-starlette/README.md:22-24`) | not yet | 7 |
| taskiq | 2 (1 action; `../modern-di-taskiq/modern_di_taskiq/main.py:19-31`) | 1 (`../modern-di-taskiq/README.md:34-70`) | 1 (`../modern-di-taskiq/modern_di_taskiq/main.py:19-31` owns both sides; documented `run_receiver_task(run_startup=False)` caveat, `docs/integrations/taskiq.md:67-72`) | 2 (L=7; `../modern-di-taskiq/README.md:34-70`) | 2 (no handler decorator — `FromDI` is a `TaskiqDepends` parameter default; `../modern-di-taskiq/modern_di_taskiq/main.py:59-62`) | 1 (missing canonical-example line; `../modern-di-taskiq/README.md:22-24`) | not yet | 9 |
| typer | 1 (2 actions: `setup_di` + manual `with container:`; `../modern-di-typer/modern_di_typer/main.py:18-24`, `../modern-di-typer/README.md:59-61`) | 1 (`../modern-di-typer/README.md:32-62`) | 0 (`setup_di` owns neither side: root is opened manually via `with container:`, `README.md:59-61`; the per-command child is built inside `@inject`'s wrapper, not by `setup_di`, `../modern-di-typer/modern_di_typer/main.py:18-24,31-34,69-83`) | 1 (L=9; `../modern-di-typer/README.md:32-62`) | 1 (@inject required, inherent — command params are CLI parsing (`typer.Option`/`Argument`), no per-param provider seam; `docs/integrations/typer.md:72`, `../modern-di-typer/modern_di_typer/main.py:52-86`) | 1 (missing canonical-example line; `../modern-di-typer/README.md:22-24`) | not yet | 5 |

### D5 rationale

D5 measures `@inject` avoidability. The **decorator-free four** (D5=2) all resolve
`FromDI` markers through the host framework's own per-parameter dependency hook, so the
marker lives as a parameter default and no handler decorator is needed: fastapi via
`fastapi.Depends`, litestar via `Provide`, faststream via `faststream.Depends`, taskiq
via `TaskiqDepends`. That hook is the seam. The **eight `@inject` integrations** each
lack an equivalent per-parameter provider-evaluation hook, so `@inject` is **inherent
(D5=1)** — every one is a 1, none a 0 (no framework exposes an unused seam):

- **flask → 1 (inherent).** "Flask has no dependency-injection system of its own …
  there is no `Depends`" (`docs/integrations/flask.md:3-4`); a view is a plain callable.
  No per-parameter provider seam. (`auto_inject` still applies `@inject` under the hood
  by wrapping `app.view_functions`, `../modern-di-flask/modern_di_flask/main.py:46-52` —
  an adapter convenience, not a framework seam.)
- **starlette → 1 (inherent).** "Starlette has no dependency-injection system of its
  own … there is no `Depends`" (`docs/integrations/starlette.md:3-4`); endpoints are
  plain ASGI callables. No per-parameter provider seam.
- **aiohttp → 1 (inherent).** "aiohttp has no dependency-injection system of its own"
  (`docs/integrations/aiohttp.md:3`); a handler is `async def handler(request)`. No
  per-parameter provider seam.
- **celery → 1 (inherent).** A task is a plain callable invoked with its own arguments;
  the adapter must strip `FromDI` params from the visible signature and resolve them
  itself (`../modern-di-celery/modern_di_celery/main.py:69-79`). No per-parameter
  provider seam. (`DITask` auto-applies `@inject` to `run`, main.py:91-97 — adapter
  convenience, not a framework seam.)
- **arq → 1 (inherent).** arq calls the task as `coroutine(ctx, *args, **kwargs)`
  (`../modern-di-arq/modern_di_arq/main.py:134-135`); `ctx` is a plain dict with no
  per-parameter provider hook. No seam.
- **aiogram → 1 (inherent; closest call).** "aiogram has no dependency-injection system
  of its own" (`docs/integrations/aiogram.md:3`). aiogram *does* have **name-based
  contextual-data injection** (middleware `data` dict → handler kwargs matched by
  parameter name), and the adapter uses it to pass the child container. But that
  mechanism matches by *name* and never evaluates a parameter *default* as a provider
  the way `Depends`/`Provide` do, so it cannot consume a `FromDI` marker — `@inject` is
  required to read the markers and resolve them
  (`../modern-di-aiogram/modern_di_aiogram/main.py:62-90`). No per-parameter
  provider-evaluation seam ⇒ 1. (See Concerns.)
- **typer → 1 (inherent).** Command parameter defaults are CLI parsing declarations
  (`typer.Option`/`typer.Argument`), not a DI hook; the adapter rewrites the signature
  to strip `FromDI` params (`../modern-di-typer/modern_di_typer/main.py:52-86`;
  `docs/integrations/typer.md:72`). No per-parameter provider seam.
- **grpc → 1 (inherent).** "gRPC always calls a servicer method as `(request,
  context)`" — a fixed signature (`docs/integrations/grpc.md:177-178`). No
  per-parameter provider seam.

## §3 Per-integration notes

**litestar — blessed-ready (Σ=12).** All six dimensions score 2: one-call setup
(`main.py:64-70`), a dedicated linked starter (`README.md:24`), `setup_di` owns both
root and per-request lifecycle with no documented root-open caveat (`main.py:64-70`),
L=7 (`README.md:34-97`), no handler decorator (`Provide`, `main.py:92-93`), and a fully
ordered README (`README.md:1-154`). No gaps to name.

**fastapi — not yet (Σ=11), the closest miss.** D1, D2, D4, D5, D6 all score 2; only
D3=1 blocks: `setup_di` owns both root and per-request lifecycle (`main.py:47-60`), but
there is a documented mounted-sub-app/disabled-lifespan caveat where the root's open
hook does not fire (`docs/integrations/fastapi.md:66-73`).

**faststream — not yet (Σ=9).** D1, D4, D5 score 2. D2=1: inline `README.md:34-67`
Usage block only, no dedicated starter. D3=1: `setup_di` owns both sides
(`main.py:60-78`) but a documented `TestBroker`/`TestApp` root-open caveat applies
(`docs/integrations/faststream.md:125-131`). D6=1: missing canonical-example line
(`README.md:22-24`).

**taskiq — not yet (Σ=9).** D1, D4, D5 score 2. D2=1: inline `README.md:34-70` Usage
block only, no dedicated starter. D3=1: `setup_di` owns both sides (`main.py:19-31`)
but a documented `run_receiver_task(run_startup=False)` root-open caveat applies
(`docs/integrations/taskiq.md:67-72`). D6=1: missing canonical-example line
(`README.md:22-24`).

**aiogram — not yet (Σ=8).** D1 and D3 score 2. D2=1: inline `README.md:34-63` Usage
block only, no dedicated starter. D4=1: L=8, one line over the ≤7 bar
(`README.md:34-63`). D5=1: `@inject` required and inherent — aiogram's name-based
contextual injection can't evaluate `FromDI` marker defaults, no per-param seam
(`main.py:62-90`). D6=1: missing canonical-example line (`README.md:22-24`).

**aiohttp — not yet (Σ=8).** D1 and D3 score 2. D2=1: inline `README.md:34-69` Usage
block only, no dedicated starter. D4=1: L=8 (`README.md:34-69`). D5=1: `@inject`
required and inherent — no DI seam, handler is `async def handler(request)`
(`docs/integrations/aiohttp.md:3`). D6=1: missing canonical-example line
(`README.md:22-24`).

**arq — not yet (Σ=8).** D1 and D3 score 2. D2=1: inline `README.md:34-75` Usage block
only, no dedicated starter. D4=1: L=8 (`README.md:34-75`). D5=1: `@inject` required and
inherent — arq calls the task as `coroutine(ctx, *args, **kwargs)`, no per-param seam
(`main.py:134-135`). D6=1: missing canonical-example line (`README.md:22-24`).

**celery — not yet (Σ=7).** Only D1 scores 2. D2=1: inline `README.md:34-71` Usage
block only, no dedicated starter. D3=1: `setup_di` owns the root only (`main.py:15-41`);
the per-task child is owned by `@inject`/`DITask`, not `setup_di` (`main.py:54-88`), and
a `task_always_eager` root-open caveat is documented (`README.md:73`). D4=1: L=8
(`README.md:34-71`). D5=1: `@inject` required and inherent — a task is a plain callable
invoked with its own args, no per-param seam (`main.py:54-88`). D6=1: missing
canonical-example line (`README.md:22-24`).

**starlette — not yet (Σ=7).** Only D1 scores 2. D2=1: inline `README.md:34-72` Usage
block only, no dedicated starter. D3=1: `setup_di` owns both sides (`main.py:73-78`) but
a documented mounted-sub-app/disabled-lifespan root-open caveat applies
(`docs/integrations/starlette.md:74-81`). D4=1: L=8 (`README.md:34-72`). D5=1: `@inject`
required and inherent — no DI seam, endpoint is a plain ASGI callable
(`docs/integrations/starlette.md:3-4`). D6=1: missing canonical-example line
(`README.md:22-24`).

**flask — not yet (Σ=6).** D1=1: two actions — `setup_di` plus a manual
`container.open()` (`main.py:28-43`, `README.md:63-65`). D2=1: inline `README.md:34-66`
Usage block only, no dedicated starter. D3=1: `setup_di` owns only the per-request
child; root teardown is manual (`docs/integrations/flask.md:123-127`). D4=1: L=9
(`README.md:34-66`). D5=1: `@inject` required and inherent — no DI seam, view is a
plain callable (`docs/integrations/flask.md:3-4`). D6=1: missing canonical-example line
(`README.md:22-24`).

**grpc — not yet (Σ=5), a hard fail.** D1=1: two actions — manual
`container.open()`/`close_sync()` plus `DIInterceptor` registration
(`README.md:75-84`). D2=1: inline `README.md:34-85` Usage block only, no dedicated
starter. D3=1: `DIInterceptor` owns only the per-RPC child; root lifecycle is manual
(`README.md:87`, `docs/integrations/grpc.md:153-162`). D4=0: L=10, at/over the ≥10 bar
(`README.md:34-85`). D5=1: `@inject` required and inherent — gRPC always calls a
servicer method as fixed `(request, context)`, no per-param seam
(`docs/integrations/grpc.md:177-178`). D6=1: missing canonical-example line
(`README.md:22-24`).

**typer — not yet (Σ=5), a hard fail.** D1=1: two actions — `setup_di` plus a manual
`with container:` (`main.py:18-24`, `README.md:59-61`). D2=1: inline `README.md:32-62`
Usage block only, no dedicated starter. D3=0: `setup_di` owns neither side — the root
is opened manually via `with container:` (`README.md:59-61`) and the per-command child
is built inside `@inject`'s wrapper, not by `setup_di` (`main.py:18-24,31-34,69-83`).
D4=1: L=9 (`README.md:32-62`). D5=1: `@inject` required and inherent — command
parameters are CLI parsing declarations (`typer.Option`/`Argument`), no per-param seam
(`docs/integrations/typer.md:72`). D6=1: missing canonical-example line
(`README.md:22-24`).

## §4 Prioritized backlog

Ranked by leverage (integrations touched / newcomer-facing weight) × cost (docs vs
code vs new repo). The `not yet` integration with the fewest, cheapest sub-2 dims
ranks first, since it is the cheapest path to a second blessed-ready row.

1. **fastapi — close the D3 root-open caveat (Σ=11, only D3=1 blocks the verdict).**
   Leverage: flips one integration to blessed-ready — the single cheapest verdict
   flip available, since D1/D2/D4/D5/D6 already score 2 (§2 fastapi row). Cost:
   likely doc-only or unfixable — the caveat is a mounted-ASGI-sub-app /
   disabled-lifespan deployment context where the root's open hook structurally
   cannot fire (`docs/integrations/fastapi.md:66-73`), the same class of limit as
   D5's inherent `@inject`. **Tag: per-integration.** First action: confirm whether
   any code-level mitigation exists before accepting it as a documented, permanent
   D3=1 (mirroring the D5 rationale's "inherent, not a gap" treatment).

2. **Build canonical starter templates and link them — 10 of 12 lack D2=2, the
   identical 10 lack D6's canonical-example line.** Leverage: the single biggest
   cross-cutting gap — 10 of 12 integrations, and D2 is one of the three
   verdict-blocking essentials (§1 verdict rule). Grounding: §2 shows D2=1 for
   aiogram, aiohttp, arq, celery, faststream, flask, grpc, starlette, taskiq,
   typer (inline Usage block only, generic "browse templates" footer — each
   row's own Usage-block cite already in §2); the same 10 are D6=1 for the
   identical missing canonical-example line (the `README.md:22-24` pattern
   repeated across all 10 rows). §5 Finding 2 re-confirms
   only fastapi and litestar link a dedicated starter. Cost: split in two —
   building a runnable starter per framework is code/new-repo work (highest cost
   item here); once a starter exists, adding the README's `Usage example:` line
   is a one-line docs fix. **Tag: templates** (build) **+ README-normalization**
   (link).

3. **`@inject`-asymmetry thread — document the rationale, do not unify.**
   Leverage: cross-cutting (all 8 `@inject` integrations), but the fix is
   explanatory, not code. Grounding: §2's D5 rationale (lines 85–129) shows all 8
   score D5=1 (inherent) and none scores 0 (avoidable-but-not-avoided) — §5
   Finding 4 re-confirms via the fresh `@inject` grep split. Cost: low — write
   down, once, why decorator-free vs `@inject` splits along "does the framework
   expose a per-parameter provider-evaluation hook," so newcomers read it as a
   framework constraint rather than an inconsistency in modern-di. **Tag:
   @inject-asymmetry.**

4. **faststream, taskiq — close the D3 root-open caveat (Σ=9 each, same pattern as
   item 1).** Leverage: 2 integrations, next-closest to blessed-ready once item 2
   lands (D2/D6 fixed, leaving only D3). Grounding: faststream's `TestBroker`/
   `TestApp` caveat (`docs/integrations/faststream.md:125-131`) and taskiq's
   `run_receiver_task(run_startup=False)` caveat (`docs/integrations/taskiq.md:67-72`)
   — both documented-deployment-context gaps like fastapi's, not code omissions.
   Cost: same as item 1 — verify unfixability before accepting as permanent.
   **Tag: per-integration.**

5. **aiogram, aiohttp, arq — trim the quickstart by one line (Σ=8 each, D4=1 at
   L=8).** Leverage: 3 integrations, one line over the D4 ≤7 bar
   (`README.md:34-63`, `:34-69`, `:34-75` respectively). D5=1 for all three is
   inherent (§2 D5 rationale) and not part of this item. Cost: low — a quickstart
   rewrite is a docs edit, not a code change; once item 2 lands these three also
   pick up D2/D6. **Tag: README-normalization.**

6. **celery, starlette — close D3 (Σ=7 each, next-worst lifespan gap).** Leverage:
   2 integrations. Cost differs per-row: starlette's D3=1 is the same
   mounted-sub-app/disabled-lifespan caveat as fastapi
   (`docs/integrations/starlette.md:74-81`) — likely unfixable, same treatment as
   item 1. Celery's D3=1 is architecturally different and code-fixable: `setup_di`
   owns only the root; the per-task child scope is opened inside `@inject`/
   `DITask`, not `setup_di` (`../modern-di-celery/modern_di_celery/main.py:54-88`),
   plus a `task_always_eager` caveat (`README.md:73`) — closing the child-scope
   half is a real adapter change. **Tag: per-integration.**

7. **flask — wire root lifecycle into `setup_di` (Σ=6, D1=1 and D3=1 share one
   root cause).** Leverage: 1 integration, but fixes two dimensions at once — both
   gaps trace to the same fact: `setup_di` owns only the per-request child, so the
   user manually calls `container.open()` (D1's second action) and owns root
   teardown by hand (D3's manual half) — `../modern-di-flask/modern_di_flask/main.py:28-43`,
   `docs/integrations/flask.md:123-127`. Cost: moderate code change (wrap root
   open/close into `setup_di`, e.g. via a Flask app-context teardown hook).
   **Tag: per-integration.**

8. **grpc — hard fail (Σ=5, D4=0, worst quickstart).** Leverage: 1 integration.
   Cost: highest of the per-integration items — needs both a lifecycle fix (root
   lifecycle is manual, `DIInterceptor` owns only the per-RPC child,
   `../modern-di-grpc/README.md:87`) and a quickstart trim from L=10 down to ≤9
   (ideally ≤7) to clear the D4=0 hard-fail bar. **Tag: per-integration.**

9. **typer — hard fail (Σ=5, D3=0, only integration where `setup_di` owns neither
   lifecycle side).** Leverage: 1 integration. Cost: highest-risk architecture
   change — the root is opened manually via `with container:`
   (`README.md:59-61`) and the per-command child scope is built inside
   `@inject`'s wrapper rather than `setup_di`
   (`../modern-di-typer/modern_di_typer/main.py:18-24,31-34,69-83`), so fixing D3
   means routing command invocation itself through `setup_di`. **Tag:
   per-integration.**

## §5 Cross-cutting findings

**Finding 1 — the `@inject` split is 4-vs-8, re-confirming §2 D5.** Fresh grep,
2026-07-23, `for d in …; do grep -c "@inject" ../modern-di-$d/README.md; done`:

```
aiogram @inject=4
aiohttp @inject=3
arq @inject=2
celery @inject=3
fastapi @inject=0
faststream @inject=0
flask @inject=4
grpc @inject=3
litestar @inject=0
starlette @inject=3
taskiq @inject=0
typer @inject=2
```

Zero-count READMEs — fastapi, faststream, litestar, taskiq — are exactly the 4
rows §2 scores D5=2 (no handler decorator). Nonzero READMEs — aiogram, aiohttp,
arq, celery, flask, grpc, starlette, typer — are exactly the 8 rows §2 scores
D5=1. **No discrepancy; §2 stands as re-verified**, including grpc, which the
originating change file (`planning/changes/2026-07-22.01-blessed-ready-onramp-audit.md`)
flagged as missing from an earlier "7 of 12" count — this audit's §2 already
carries grpc as the 8th `@inject` integration.

**Finding 2 — exactly 2 of 12 READMEs link a dedicated starter, re-confirming §2
D2.** Fresh grep, `grep -q "Usage example:" ../modern-di-$d/README.md`:

```
fastapi: dedicated starter
litestar: dedicated starter
```

Only fastapi and litestar matched — exactly the 2 rows §2 scores D2=2. The other
10 are D2=1 (inline Usage block only). **No discrepancy.**

**Finding 3 — no integration ships an `examples/` dir.** `[ -d
../modern-di-$d/examples ]` produced no output for any of the 12 subjects — the
loop completed with zero hits. This confirms the spec's opening premise (the
FastAPI and Litestar SQLAlchemy templates, linked externally, are the only
canonical starters anywhere in the ecosystem; nothing is vendored as an
in-repo `examples/` tree by any adapter). **No discrepancy.**

**Finding 4 — D5 has no 0s: the `@inject`-asymmetry thread is "document," not
"unify."** Across the 8 `@inject`-requiring integrations, §2's D5 rationale
(report lines 85–129) traces each to the same root cause — the host framework
exposes no per-parameter provider-evaluation hook (no `Depends`-equivalent) — so
`@inject` is inherent, never avoidable-but-unused. Every one of the 8 scores 1;
none scores 0. Combined with Finding 1's grep, the split is real and consistent,
not an oversight: the fix is a documentation thread (§4 item 3), not a code
unification.

**Finding 5 — D3's 8 sub-2 rows split into two different root causes, which
changes their fix cost.** Four rows (fastapi, faststream, taskiq, starlette)
score D3=1 for a **documented deployment-context caveat only** — `setup_di`
already owns both sides in code, but a specific runtime context prevents the
root hook from firing (mounted ASGI sub-app / disabled lifespan for fastapi and
starlette, `TestBroker`/`TestApp` for faststream, `run_receiver_task(run_startup=False)`
for taskiq). These look structurally like D5's inherent limits and may not be
code-fixable. Three rows (flask, grpc, typer) score D3=1 or D3=0 for a different
reason — `setup_di` (or its equivalent hook) literally does not own root
lifecycle in the normal code path, no caveat needed — which **is** a
code-fixable adapter gap. Celery is the one **hybrid** row: it carries both
patterns at once — `setup_di` owns the root but not the per-task child scope
(the flask/grpc-style code gap, `../modern-di-celery/modern_di_celery/main.py:54-88`)
*and* a documented `task_always_eager` root-open caveat (`README.md:73`). §4
tags the caveat-only group for verification-then-accept (per-integration, low
cost) and the code-gap group (plus celery's code-gap half) for a real lifecycle
rewrite (per-integration, higher cost).

## Appendix: modern-di-pytest (not scored)

`modern-di-pytest` is excluded from this audit's scoring — as a pytest plugin
its on-ramp shape (fixture-driven container construction and reset semantics)
differs from the app-framework setup_di/lifespan/handler-decorator axes §1
scores; see `docs/integrations/pytest.md` for its own onboarding guide.
