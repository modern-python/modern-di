---
status: accepted
summary: The @inject asymmetry (4 integrations decorator-free, 8 require @inject) is inherent, not an adapter gap — @inject is required exactly where the host framework exposes no per-parameter provider seam; do not unify, document the rationale.
supersedes: null
superseded_by: null
---

# The @inject asymmetry is inherent — do not unify

**Decision:** The four integrations that resolve `FromDI` decorator-free
(fastapi, litestar, faststream, taskiq) and the eight that require `@inject`
(flask, starlette, aiohttp, celery, arq, aiogram, typer, grpc) keep their current
shapes. The split is inherent — an adapter can drop `@inject` only where the host
framework offers a per-parameter provider seam, and the eight offer none — so
there is nothing to unify. Treatment is this documented rationale.

## Context

The 2026-07-22 blessed-ready on-ramp audit's
**D5** dimension scores whether a handler needs a DI decorator: **2** = none, **1**
= `@inject` required but inherent (no framework seam), **0** = `@inject` required
but a seam exists the adapter fails to use. The audit found the split is **4 vs 8**
(not the adoption research's stale "7 of 12"), and — the substantive question this
records — **every one of the eight is a 1, never a 0**: no framework exposes an
unused seam.

The seam test: `FromDI` can live as a bare parameter *default* (no decorator)
only where the framework itself evaluates a parameter's default as a provider.

| Integration | D5 | Per-parameter provider seam | Verdict |
|---|---|---|---|
| fastapi | 2 | `fastapi.Depends` | decorator-free |
| litestar | 2 | `Provide` | decorator-free |
| faststream | 2 | `faststream.Depends` | decorator-free |
| taskiq | 2 | `TaskiqDepends` | decorator-free |
| flask | 1 | none — view is a plain callable, no `Depends` | inherent |
| starlette | 1 | none — endpoint is a plain ASGI callable | inherent |
| aiohttp | 1 | none — handler is `async def handler(request)` | inherent |
| celery | 1 | none — task is a plain callable with its own args | inherent |
| arq | 1 | none — `coroutine(ctx, …)`, `ctx` a plain dict | inherent |
| aiogram | 1 | name-based `data` injection, **not** provider-evaluation (closest call) | inherent |
| typer | 1 | none — defaults are CLI parsing (`Option`/`Argument`) | inherent |
| grpc | 1 | none — fixed `(request, context)` servicer signature | inherent |

## Decision & rationale

`@inject` is required in the eight **precisely because** their frameworks call a
handler with a fixed signature and expose no per-parameter provider-evaluation
hook. Where such a hook exists (the four), the adapter binds `FromDI` to it and
the decorator disappears; where it does not, `@inject` is the only way to read the
markers off the signature and resolve them. An adapter cannot manufacture a seam
the framework does not have. So the asymmetry is a property of the host
frameworks, not a modern-di shortfall, and "unify the eight to decorator-free" is
not achievable in code.

**aiogram is the one close call.** aiogram *does* have name-based contextual-data
injection (a middleware `data` dict matched to handler kwargs by parameter name),
which the adapter uses to pass the child container. But it matches by name and
never evaluates a parameter *default* as a provider the way `Depends`/`Provide`
do, so it cannot consume a `FromDI` marker — `@inject` is still required. Ruled 1,
not 0.

**Positioning follows from this.** The defensible claim is *no `@provide` ever, and
no `@inject` in the four biggest integrations* (where dishka needs `@inject` even
for FastAPI/Litestar), not "decorator-free" unqualified — which a single `grep`
refutes. The adapter-side `auto_inject` (Flask) and `DITask` (Celery) helpers apply
`@inject` under the hood for convenience; they are not framework seams and do not
change the verdict.

**Consistency.** Same call as the
[D3 root-lifecycle gaps ruled inherent](2026-07-25-d3-root-lifecycle-inherent.md)
and the [exec hot-path re-decline](2026-07-19-exec-hot-path-declined.md): where a
sub-2 score reflects a framework limitation rather than a modern-di gap, document
the deliberate stance instead of adding machinery to move it.

## Revisit trigger

A Category-8 framework gains a per-parameter dependency hook it currently lacks
(e.g. a future Flask/Starlette DI feature) — its integration should then bind
`FromDI` to that hook and drop `@inject`, reopening its row. Or a user reports the
`@inject` requirement as real adoption friction in a specific integration.
