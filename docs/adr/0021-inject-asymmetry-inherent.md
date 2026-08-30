# The @inject asymmetry is inherent — do not unify

**Decision:** the four integrations that resolve `FromDI` decorator-free (fastapi, litestar,
faststream, taskiq) and the eight that require `@inject` (flask, starlette, aiohttp, celery, arq,
aiogram, typer, grpc) keep their current shapes. An adapter can drop `@inject` only where the host
framework evaluates a parameter *default* as a provider, and the eight offer no such seam, so there
is nothing to unify.

| Integration | Per-parameter provider seam | Verdict |
|---|---|---|
| fastapi | `fastapi.Depends` | decorator-free |
| litestar | `Provide` | decorator-free |
| faststream | `faststream.Depends` | decorator-free |
| taskiq | `TaskiqDepends` | decorator-free |
| flask | none — view is a plain callable | inherent |
| starlette | none — endpoint is a plain ASGI callable | inherent |
| aiohttp | none — handler is `async def handler(request)` | inherent |
| celery | none — task is a plain callable with its own args | inherent |
| arq | none — `coroutine(ctx, …)`, `ctx` a plain dict | inherent |
| aiogram | name-based `data` injection, **not** provider-evaluation (closest call) | inherent |
| typer | none — defaults are CLI parsing (`Option`/`Argument`) | inherent |
| grpc | none — fixed `(request, context)` servicer signature | inherent |

**aiogram is the one close call.** Its middleware `data` dict is matched to handler kwargs by
parameter *name* and never evaluates a default as a provider, so it cannot consume a `FromDI`
marker; the adapter uses it only to pass the child container.

**Positioning follows.** The defensible claim is *no `@provide` ever, and no `@inject` in the four
biggest integrations* (where dishka needs `@inject` even for FastAPI/Litestar), not "decorator-free"
unqualified, which a single `grep` refutes. The adapter-side `auto_inject` (Flask) and `DITask`
(Celery) helpers apply `@inject` under the hood for convenience; they are not framework seams.

**Quickstart length follows from this, not from anything separate.** The decorator-free floor for a
minimal single-dependency example is 7 DI-specific lines (two imports, a `Group` with one provider
and its dependency, `Container(...)`, `setup_di`), and a minimal example needs both providers to
demonstrate DI at all, so the floor cannot drop. Against the merged examples: aiogram, aiohttp and
arq are at 8 — the floor plus the `@inject` line; flask and typer at 9 — plus the manual root
`open()`/`with` ruled inherent in [the root-lifecycle record](0020-d3-root-lifecycle-inherent.md);
grpc at 10, plus `close_sync()`. Nothing is trimmable without deleting an inherent element, so there
is no independent quickstart fix.

Same call as [the D3 root-lifecycle gaps](0020-d3-root-lifecycle-inherent.md) and
[the exec hot-path re-decline](0017-exec-hot-path-declined.md): where a gap reflects a framework
limitation rather than a modern-di shortfall, document the stance instead of adding machinery.

**Revisit trigger:** an `@inject`-requiring framework gains a per-parameter dependency hook (a
future Flask/Starlette DI feature) — its integration should then bind `FromDI` to that hook and drop
`@inject`, reopening its row. Or a user reports the `@inject` requirement as real adoption friction
in a specific integration.
