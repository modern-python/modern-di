# modern-di vs other libraries

modern-di isn't the only way to do dependency injection in Python. This is an
honest look at where it fits — including when you don't need a DI container at
all.

## Do you even need a DI container?

If you're building a single FastAPI or Litestar service and everything you
inject is request-scoped (a database session, the current user, settings), the
framework's own DI — FastAPI's `Depends`, Litestar's `Provide` — is enough, and
a standalone container is overkill.

Reach for a container when one of these is true:

- **More than one entrypoint.** An API *and* a worker (FastStream/Celery) *and*
  a CLI (Typer), all sharing one wiring instead of three parallel copies.
- **Typed, app-scoped singletons with real teardown** — instead of an untyped
  `app.state` bag plus `lru_cache` with no cleanup.
- **Resolution off the request path** — in startup, background tasks, workers, or
  CLI commands, where `Depends`/`Provide` simply don't run.
- **Whole-app test overrides** — swap a dependency once and have every entrypoint
  (HTTP, worker, CLI, direct unit tests) see it, not just code reached through
  the HTTP layer.

modern-di's core promise is exactly that: **one typed wiring shared across
FastAPI, Litestar, FastStream, and Typer.**

## The landscape

| | modern-di | Dishka | dependency-injector | injector | FastAPI `Depends` |
|---|---|---|---|---|---|
| Style | type-based autowiring | type-based, provider classes | declarative containers + markers | Guice-style `@inject` | callable-based |
| Scopes | APP→…→STEP (fixed chain) | RUNTIME→…→STEP (+ custom) | lifetimes (Singleton/Factory/Resource) | Singleton / Thread / None | request only |
| Resolution | sync (by design) | sync + async | sync + async | sync | async |
| First-party pytest plugin | ✅ | ✘ | ✘ | ✘ | n/a |
| Official integrations | 5 (FastAPI, Litestar, FastStream, Typer, pytest) | ~20+ | FastAPI, Flask, … | Flask (1st-party), FastAPI (3rd-party) | n/a |
| Typed resolution | ✅ | ✅ | partial | ✅ | callable-keyed |
| License | MIT | Apache-2.0 | BSD-3 | BSD | — |
| Adoption | newest, very active | established, large community | most popular, mature | mature | built into FastAPI |

## Honest comparison

### vs Dishka

Dishka is the closest library to modern-di — also typed, also scopes-first, also
integrating with FastAPI/Litestar/FastStream — and it's more established, with
many more integrations and a larger community. If you need **arbitrary custom
scopes**, **async resolution**, or an integration modern-di doesn't have yet
(aiogram, Taskiq, gRPC, …), Dishka is an excellent choice.

modern-di's deliberate differences:

- **A first-party pytest plugin** (`modern-di-pytest`) that turns any dependency
  into a fixture — Dishka has no built-in pytest integration yet.
- **Sync-only resolution and a small, fixed scope chain** — a simpler model.
  Dishka's own docs note that custom scopes are "hardly ever needed," which is
  the honest case for modern-di's simpler design.
- **All-official, uniformly-maintained integrations** under a single MIT-licensed
  project, as part of the broader [modern-python](https://github.com/modern-python)
  stack.

### vs dependency-injector

`dependency-injector` is the most popular Python DI library, with a mature,
Cython-accelerated core and a declarative style using `Provide[...]` markers and
`@inject`. It is actively maintained again after an earlier hiatus. modern-di
differs in style — **type-based autowiring instead of explicit markers** — and
adds **nested request scopes** and a **first-party pytest plugin**. If you prefer
explicit declarative wiring and the largest ecosystem, dependency-injector is a
solid, proven choice.

### vs injector

`injector` is a Guice-inspired, mature library with `@inject` and `Module`-based
configuration. Its core has **no async support** and **no nested request scope**
(request scoping comes from third-party FastAPI adapters). modern-di offers
built-in scopes, official framework integrations, and resource finalization out
of the box.

### vs framework-native (`Depends` / `Provide`)

For a single web service, native DI is simpler and a container is overkill — see
[Do you even need a DI container?](#do-you-even-need-a-di-container) above.
modern-di earns its place once you have a second entrypoint, or need typed,
scoped, app-wide singletons with overrides that work everywhere, not just on the
HTTP path.

## See also

- [Design decisions](design-decisions.md) — the reasoning behind sync-only
  resolution, no global state, and a conservative core.
- [that-depends or modern-di?](that-depends-or-modern-di.md) — choosing within
  the modern-python family.
