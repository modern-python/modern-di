# modern-di vs other libraries

Where modern-di fits among Python's DI libraries, what it leaves out, and when you can skip a DI
container.

## Do you need a DI container?

A single FastAPI or Litestar service can get by with the framework's own DI (FastAPI's `Depends`,
Litestar's `Provide`), and a small one whose dependencies are all request-scoped usually does. A
container still pays off in a single service, and more as the app grows:

- App-scoped objects (a database engine, an HTTP client, settings) get typed providers with
  teardown. `Depends` has no app scope, so the usual alternative is an untyped `app.state` bag plus
  `lru_cache` with no cleanup.
- Service classes keep plain constructors. With `Depends`, a class that needs a repository declares
  `Annotated[Repo, Depends(get_repo)]` in its `__init__`, which ties it to FastAPI.
- Tests can override a dependency once for everything: HTTP calls, workers, CLI commands and direct
  unit tests that never touch the app. `app.dependency_overrides` reaches only calls made through
  the app. `container.validate()` checks the whole graph in one test.
- A second entrypoint, such as a worker (FastStream, Celery) or a CLI (Typer), shares the same
  wiring instead of a parallel copy, and so does code that runs off the request path: startup and
  background tasks.

modern-di adds 1.74 µs to a request cycle on the [benchmark machine](performance.md), and its
wiring is shared across thirteen frameworks: aiogram, aiohttp, arq, Celery, FastAPI, FastMCP,
FastStream, Flask, gRPC, Litestar, Starlette, taskiq, and Typer.

## Feature comparison

| | modern-di | Dishka | dependency-injector | wireup | that-depends | injector |
|---|---|---|---|---|---|---|
| Style | `Factory` providers in a `Group`, wired by type | `Provider` classes, wired by type | declarative containers + `Provide[...]` markers | `@injectable` classes and factories, wired by type | providers on a container class | Guice-style `Module` bindings + `@inject` |
| Scopes | APP→…→STEP + any `IntEnum` | APP→…→STEP + custom | none; lifetime comes from the provider type | singleton / scoped / transient | named context scopes (APP, REQUEST, custom) | singleton / thread-local / none + custom |
| Async resolution | ❌ (async finalizers ✅) | ✅ | ✅ | ✅ | ✅ | ❌ |
| Graph validation before first resolve | `container.validate()`, called explicitly | automatic at container build | `check_dependencies()`, undefined dependencies only | automatic at container creation | ❌ | ❌ |
| Test override | `container.override(provider, mock)` | a provider with `override=True` | `provider.override(mock)` | `container.override({Type: fake})` | `provider.override_sync(mock)` | no API; build the injector from test modules |
| First-party pytest plugin | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Integrations | 13 frameworks + a pytest plugin | 13 built in + 10 community | wiring works with any framework; `ext` module for Starlette | 10, including Django and FastMCP | FastAPI, FastStream | none bundled; `flask_injector` (same org), `fastapi-injector` (third party) |
| Typed resolution | ✅ | ✅ | partial (`Provide[...]` is `Any`) | ✅ | ✅ | ✅ |
| Speed vs modern-di | n/a | [modern-di faster in 4 of 5 scenarios](performance.md#at-a-glance) | [modern-di faster in 4 of 5](performance.md#at-a-glance) | [modern-di faster in 4 of 5](performance.md#at-a-glance) | [modern-di faster in 4 of 5](performance.md#at-a-glance) | not benchmarked |
| License | MIT | Apache-2.0 | BSD-3 | MIT | MIT | BSD-3 |
| GitHub stars (2026-10-10) | 66 | 1.3k | 4.9k | 437 | 254 | 1.5k |

The library columns were checked against Dishka 1.10.1, dependency-injector 4.49.1, wireup 2.12.1,
that-depends 4.2.0 and injector 0.24.0.

On typed resolution: `resolve(SomeType)` is typed `SomeType`, and the integration marker
`Annotated[T, from_di(dep)]` type-checks as `T`, the same shape as Dishka's `FromDishka[T]` and
FastAPI's `Annotated[T, Depends(...)]`. dependency-injector's `Provide[...]` marker is typed `Any`,
and its `Provider[Animal]` annotation infers the base `Animal` instead of a concrete subtype. A bare
`x = Depends(fn)` is typed `Any` too. modern-di's typing needs no type-checker plugin; see the
[non-goal on static wiring verification](design-decisions.md#static-compile-time-wiring-verification-a-type-checker-plugin).

## What modern-di leaves out

These are [non-goals](design-decisions.md#non-goals). If you need one, another library fits better.

- Async resolution: Dishka, dependency-injector, wireup and that-depends can await an async
  factory. modern-di resolves synchronously; async setup belongs in your framework's lifespan
  (see [Async resources via lifespan](../recipes/async-lifespan.md)), and async teardown in a
  finalizer.
- Collection injection: one type has one provider. To inject a list, write a `Factory` that
  takes the individual dependencies and returns the list
  ([why](design-decisions.md#multibinding-collection-injection)).
- Generator factories: wireup and Dishka run the code after `yield` as teardown. modern-di takes
  the teardown as `CacheSettings(finalizer=...)`
  ([why](design-decisions.md#generator-creators-teardown-after-yield)).
- Auto-registration: modern-di never registers a provider you did not declare, so a missing one
  shows up in `validate()` ([why](design-decisions.md#auto-binding-auto-registration)).

## Library by library

### vs Dishka

Dishka is the closest library to modern-di: typed, built around scopes, and integrated with FastAPI
and Litestar. It is older and has a larger community. Its docs list 13 built-in framework
integrations and 10 community ones, including its FastStream and Starlette support
([`dishka-faststream`](https://github.com/faststream-community/dishka-faststream) and
[`starlette-dishka`](https://github.com/reagento/starlette-dishka)); the bundled modules for those
two are deprecated. Pick Dishka if you need async resolution or an integration modern-di lacks:
aiogram-dialog, Click, Sanic or pyTelegramBotAPI built in, or Pyramid, Quart, RQ, Strawberry or
APScheduler from the community.

Where modern-di differs:

- `modern-di-pytest` turns any dependency into a fixture. Dishka has no pytest plugin; its docs
  show hand-written fixtures.
- Resolution is sync-only, with async finalizers. Both libraries have an APP→…→STEP chain that you
  can extend (see [Custom scopes](../providers/scopes.md#custom-scopes)), and Dishka's own docs say
  custom scopes are "hardly ever needed".
- Dishka validates the graph when it builds the container. modern-di validates when you call
  `validate()`, at startup or in a test.
- Every integration is MIT-licensed and lives in the [modern-python](https://github.com/modern-python)
  organization, including FastMCP, which Dishka does not list.

### vs dependency-injector

`dependency-injector` is the most popular Python DI library, with a mature, Cython-accelerated core
and a declarative style using `Provide[...]` markers and `@inject`. It is actively maintained again
after an earlier pause. modern-di wires by type instead of by marker, and adds nested request scopes,
a typed injection marker and a first-party pytest plugin. If you prefer explicit declarative wiring
and the largest community, dependency-injector is the established option. The
[migration guide](../migration/from-dependency-injector.md) maps it provider by provider.

### vs wireup

wireup is typed, MIT-licensed and wires by type, like modern-di. It validates the graph when the
container is created, supports async resolution and generator teardown, and has 10 integrations,
including Django, Click and FastMCP. Its scopes are lifetimes (singleton, scoped, transient), and its
docs say it avoids full nested scopes. modern-di has an ordered scope chain you can nest and extend,
and a pytest plugin.

### vs injector

`injector` is a mature, Guice-inspired library with `Module`-based configuration and `@inject`. Its
core has no async support, no request scope and no teardown for what it creates. Request scoping
comes from third-party FastAPI adapters. modern-di has built-in scopes, finalizers and official
framework integrations.

### vs framework-native (`Depends` / `Provide`)

For a small single service, native DI works and you can skip a container. modern-di adds typed
app-scoped objects with teardown, constructors free of `Depends`, and overrides that reach outside
the HTTP path; see [Do you need a DI container?](#do-you-need-a-di-container) above.

## that-depends or modern-di?

[`that-depends`](https://github.com/modern-python/that-depends) is a sibling project from the same
author, in the same [modern-python](https://github.com/modern-python) organization, and an earlier
take on the same design.

- For a new project, use modern-di. It has explicit scopes, no global state, a small strictly typed
  core, and separate framework adapters; see [Design decisions](design-decisions.md).
- If you already use that-depends, it is still maintained, so you don't need to migrate. Stay on it
  if you want async resolution (`await container.resolve(...)`), which modern-di will not add.
  Move when you want explicit scopes or no global state; the
  [migration guide](../migration/from-that-depends.md) maps every provider and concept.

| | that-depends | modern-di |
|---|---|---|
| Resolution | async + sync (`AsyncFactory`, `await resolve`) | sync resolution (async finalizers supported) |
| Container model | the container class is both schema and runtime | `Group` (schema) and `Container` (runtime) are separate |
| Scopes | context-based lifetimes | explicit, enforced scope chain (APP→…→STEP) |
| Global state | resolves directly from the container class | none; you create and pass containers explicitly |
| Integrations | bundled (FastAPI, FastStream) | separate adapter packages (install only what you need) |

## Where is Singleton? Cross-framework vocabulary

modern-di has no `Singleton` class. "Create once and reuse" is a scope plus `cache=True` on an
ordinary `Factory`. The tabs translate six lifetime concepts from other libraries:

=== "dependency-injector"

    | Concept | modern-di | dependency-injector |
    |---|---|---|
    | Singleton (create once, share) | [`Factory(..., scope=Scope.APP, cache=True)`](../providers/factories.md#cached-factories) | `providers.Singleton(...)` |
    | Transient (fresh instance every time) | a plain [`Factory(...)`](../providers/factories.md) with no `cache` | `providers.Factory(...)` |
    | Request-scoped | [`Factory(..., scope=Scope.REQUEST, cache=True)`](../providers/scopes.md) | `providers.Resource` + the `Closing` wiring marker |
    | Runtime value (request object, etc.) | [`ContextProvider(...)`](../providers/context.md) + `context={...}` | `providers.Configuration` / `.from_value()` |
    | Interface binding (concrete → abstract type) | [`Alias(Impl, bound_type=Interface)`](../providers/alias.md) | `providers.AbstractFactory`, overridden with a concrete `Factory` before use |
    | Test override | [`container.override(provider, mock)`](../recipes/testing-overrides.md) | `provider.override(...)`, or `with provider.override(...):` |

=== "Dishka"

    | Concept | modern-di | Dishka |
    |---|---|---|
    | Singleton (create once, share) | [`Factory(..., scope=Scope.APP, cache=True)`](../providers/factories.md#cached-factories) | `provide(Impl, scope=Scope.APP)`, cached by default within its scope |
    | Transient (fresh instance every time) | a plain [`Factory(...)`](../providers/factories.md) with no `cache` | `provide(Impl, cache=False)` |
    | Request-scoped | [`Factory(..., scope=Scope.REQUEST, cache=True)`](../providers/scopes.md) | `provide(Impl, scope=Scope.REQUEST)` |
    | Runtime value (request object, etc.) | [`ContextProvider(...)`](../providers/context.md) + `context={...}` | `from_context(provides=Type, scope=...)`, then `context={Type: value}` at scope entry |
    | Interface binding (concrete → abstract type) | [`Alias(Impl, bound_type=Interface)`](../providers/alias.md) | `alias(source=Impl, provides=Interface)` |
    | Test override | [`container.override(provider, mock)`](../recipes/testing-overrides.md) | `provide(Mock, provides=Type, override=True)` in a test provider |

=== "wireup"

    | Concept | modern-di | wireup |
    |---|---|---|
    | Singleton (create once, share) | [`Factory(..., scope=Scope.APP, cache=True)`](../providers/factories.md#cached-factories) | `@injectable` (default `lifetime="singleton"`) |
    | Transient (fresh instance every time) | a plain [`Factory(...)`](../providers/factories.md) with no `cache` | `@injectable(lifetime="transient")` |
    | Request-scoped | [`Factory(..., scope=Scope.REQUEST, cache=True)`](../providers/scopes.md) | `@injectable(lifetime="scoped")` |
    | Runtime value (request object, etc.) | [`ContextProvider(...)`](../providers/context.md) + `context={...}` | a typed constructor parameter resolved from the active scope's context |
    | Interface binding (concrete → abstract type) | [`Alias(Impl, bound_type=Interface)`](../providers/alias.md) | `@injectable(as_type=Interface)` |
    | Test override | [`container.override(provider, mock)`](../recipes/testing-overrides.md) | `with container.override({Target: fake}):` |

=== "svcs"

    | Concept | modern-di | svcs |
    |---|---|---|
    | Singleton (create once, share) | [`Factory(..., scope=Scope.APP, cache=True)`](../providers/factories.md#cached-factories) | `registry.register_value(Type, value)` at startup |
    | Transient (fresh instance every time) | a plain [`Factory(...)`](../providers/factories.md) with no `cache` | no dedicated provider; call the plain factory directly |
    | Request-scoped | [`Factory(..., scope=Scope.REQUEST, cache=True)`](../providers/scopes.md) | one instance per `svcs.Container` (built per request) |
    | Runtime value (request object, etc.) | [`ContextProvider(...)`](../providers/context.md) + `context={...}` | `registry.register_value(Type, value)`, or a per-container local factory |
    | Interface binding (concrete → abstract type) | [`Alias(Impl, bound_type=Interface)`](../providers/alias.md) | `register_factory(Interface, factory)`; svcs keys by whatever type you register under |
    | Test override | [`container.override(provider, mock)`](../recipes/testing-overrides.md) | re-call `register_value()`/`register_factory()`; `container.close()` first if already cached |

=== "FastAPI `Depends`"

    | Concept | modern-di | FastAPI `Depends` |
    |---|---|---|
    | Singleton (create once, share) | [`Factory(..., scope=Scope.APP, cache=True)`](../providers/factories.md#cached-factories) | a dependency wrapped in `@lru_cache` |
    | Transient (fresh instance every time) | a plain [`Factory(...)`](../providers/factories.md) with no `cache` | `Depends(fn, use_cache=False)` |
    | Request-scoped | [`Factory(..., scope=Scope.REQUEST, cache=True)`](../providers/scopes.md) | bare `Depends(fn)`, computed once per request by default |
    | Runtime value (request object, etc.) | [`ContextProvider(...)`](../providers/context.md) + `context={...}` | the framework injects `Request`/`WebSocket` directly by type |
    | Interface binding (concrete → abstract type) | [`Alias(Impl, bound_type=Interface)`](../providers/alias.md) | n/a (`Depends` is keyed by callable, not by type) |
    | Teardown | [`cache=CacheSettings(finalizer=cleanup)`](../providers/lifecycle.md#caching-and-finalizers), sync or async | code after `yield` in the dependency |
    | Test override | [`container.override(provider, mock)`](../recipes/testing-overrides.md), or `with container.override(...)` to reset on exit | `app.dependency_overrides[dep] = fake`, reset by hand in a `finally` |

## See also

- [Design decisions](design-decisions.md): the reasoning behind sync-only
  resolution, no global state, a conservative core, and the
  [non-goals](design-decisions.md#non-goals) that keep it that way.
- [Performance](performance.md): comparative benchmarks of how fast resolution is
  versus other DI frameworks, and the method behind the numbers.
