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
aiohttp, FastAPI, Litestar, FastStream, Starlette, and Typer.**

## The landscape

| | modern-di | Dishka | dependency-injector | injector | FastAPI `Depends` |
|---|---|---|---|---|---|
| Style | type-based autowiring | type-based autowiring (provider classes) | declarative containers + markers | Guice-style `@inject` | callable-based |
| Scopes | APP→…→STEP + any IntEnum | RUNTIME→…→STEP (+ custom) | lifetimes (Singleton/Factory/Resource) | Singleton / Thread / None | request only |
| Resolution | sync (async finalizers supported) | sync + async | sync + async | sync | async |
| First-party pytest plugin | ✅ | ✘ | ✘ | ✘ | n/a |
| Official integrations | 7 (aiohttp, FastAPI, Litestar, FastStream, Starlette, Typer, pytest) | ~20+ | FastAPI, Flask, … | Flask (1st-party), FastAPI (3rd-party) | n/a |
| Typed resolution | ✅ | ✅ | partial | ✅ | callable-keyed |
| License | MIT | Apache-2.0 | BSD-3 | BSD | — |
| Adoption | newest, very active | established, large community | most popular, mature | mature | built into FastAPI |

## Honest comparison

### vs Dishka

Dishka is the closest library to modern-di — also typed, also scopes-first, also
integrating with FastAPI/Litestar/FastStream — and it's more established, with
many more integrations and a larger community. If you need **arbitrary *named*
scopes**, **async resolution**, or an integration modern-di doesn't have yet
(aiogram, Taskiq, gRPC, …), Dishka is an excellent choice.

modern-di's deliberate differences:

- **A first-party pytest plugin** (`modern-di-pytest`) that turns any dependency
  into a fixture — Dishka has no built-in pytest integration yet.
- **Sync-only *resolution* (async finalizers still supported) and a small,
  built-in scope chain you can still extend with any `IntEnum`** — a simpler
  model. Dishka's own docs note that custom scopes are "hardly ever needed,"
  which is the honest case for modern-di's simpler design. See
  [Custom scopes](../providers/scopes.md#custom-scopes).
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
solid, proven choice. Migrating an existing codebase? See the
[migration guide](../migration/from-dependency-injector.md) for the full
provider-by-provider mapping.

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

## that-depends or modern-di?

[`that-depends`](https://github.com/modern-python/that-depends) is a sibling
project from the same author, in the same
[modern-python](https://github.com/modern-python) family — it isn't in the
table above because the choice between the two isn't about features so much
as which generation of the same design you want.

- **Starting a new project?** Use **modern-di**. It has explicit scopes, no
  global state, a small strictly-typed core, and separate framework adapters —
  see [Design decisions](design-decisions.md).
- **Already using that-depends?** It remains **actively maintained and
  production-proven** — you don't need to migrate. Move when you want explicit
  scopes or a no-global-state architecture; the
  [migration guide](../migration/from-that-depends.md) maps every concept across.

| | that-depends | modern-di |
|---|---|---|
| Resolution | async + sync (`AsyncFactory`, `await resolve`) | sync resolution (async finalizers supported) |
| Container model | the container class is both schema and runtime | `Group` (schema) and `Container` (runtime) are separate |
| Scopes | context-based lifetimes | explicit, enforced scope chain (APP→…→STEP) |
| Global state | resolves directly from the container class | none — you create and pass containers explicitly |
| Integrations | bundled | separate adapter packages (install only what you need) |

Choose **that-depends** if you specifically want async resolution
(`await container.resolve(...)` — modern-di is sync-only by design and won't
add it), want the simplest setup for a single service without an explicit
scope chain, or already run it in production with no reason to change.

The [migration guide](../migration/from-that-depends.md) covers every
provider type and concept, including the conceptual shifts: the
schema/runtime split (`Group` vs `Container`), sync-only resolution, and
explicit scopes.

## Where is Singleton? — cross-framework vocabulary

modern-di deliberately has no `Singleton` class — "create once and reuse" is spelled via a scope
plus `cache=True` on an ordinary `Factory`. Every arriving user speaks a different framework's
lifetime dialect, so here is how the same six concepts translate:

| Concept | dependency-injector | dishka | wireup | svcs | FastAPI `Depends` | modern-di |
|---|---|---|---|---|---|---|
| Singleton (create once, share) | `providers.Singleton(...)` | `provide(Impl, scope=Scope.APP)` — cached by default within its scope | `@injectable` — default `lifetime="singleton"` | `registry.register_value(Type, value)` at startup | a dependency wrapped in `@lru_cache` | [`Factory(..., scope=Scope.APP, cache=True)`](../providers/factories.md#cached-factories) |
| Transient (fresh instance every time) | `providers.Factory(...)` | `provide(Impl, cache=False)` | `@injectable(lifetime="transient")` | no dedicated provider — call the plain factory directly | `Depends(fn, use_cache=False)` | a plain [`Factory(...)`](../providers/factories.md) with no `cache` |
| Request-scoped | `providers.Resource` + the `Closing` wiring marker | `provide(Impl, scope=Scope.REQUEST)` | `@injectable(lifetime="scoped")` | one instance per `svcs.Container` (built per request) | bare `Depends(fn)` — computed once per request by default | [`Factory(..., scope=Scope.REQUEST, cache=True)`](../providers/scopes.md) |
| Runtime value (request object, etc.) | `providers.Configuration` / `.from_value()` | `from_context(provides=Type, scope=...)` declared, then `context={Type: value}` at scope entry | a typed constructor parameter resolved from the active scope's context | `registry.register_value(Type, value)`, or a per-container local factory | the framework injects `Request`/`WebSocket` directly by type | [`ContextProvider(...)`](../providers/context.md) + `context={...}` |
| Interface binding (concrete → abstract type) | `providers.AbstractFactory` — must be overridden with a concrete `Factory` before use | `alias(source=Impl, provides=Interface)` | `@injectable(as_type=Interface)` | `register_factory(Interface, factory)` — svcs keys by whatever type you register under | n/a — `Depends` is callable-keyed, not type-keyed | [`Alias(Impl, bound_type=Interface)`](../providers/alias.md) |
| Test override | `provider.override(...)`, or `with provider.override(...):` | no dedicated API — build a separate container from mock providers | `with container.override.injectable(Target, new=fake):` | re-call `register_value()`/`register_factory()`; `container.close()` first if already cached | `app.dependency_overrides[dep] = fake` | [`container.override(provider, mock)`](../recipes/testing-overrides.md) |

## See also

- [Design decisions](design-decisions.md) — the reasoning behind sync-only
  resolution, no global state, a conservative core, and the deliberate
  [non-goals](design-decisions.md#non-goals) that keep it that way.
