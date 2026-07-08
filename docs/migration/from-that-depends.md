# Migration from `that-depends`

This guide walks an existing `that-depends` codebase through the move to `modern-di`. Every provider type and core concept in `that-depends` has either a documented mapping below or an explicit note that there is no direct equivalent (with a workaround).

## 1. Install

Core package:

=== "uv"

      ```bash
      uv add modern-di
      ```

=== "pip"

      ```bash
      pip install modern-di
      ```

=== "poetry"

      ```bash
      poetry add modern-di
      ```

Framework integrations and the pytest helper live in separate packages — install only what you need:

=== "uv"

      ```bash
      uv add modern-di-fastapi      # FastAPI
      uv add modern-di-litestar     # Litestar
      uv add modern-di-faststream   # FastStream
      uv add modern-di-typer        # Typer
      uv add modern-di-pytest       # pytest fixtures
      ```

=== "pip"

      ```bash
      pip install modern-di-fastapi
      pip install modern-di-litestar
      pip install modern-di-faststream
      pip install modern-di-typer
      pip install modern-di-pytest
      ```

## 2. Key conceptual shifts

Three things change in how you think about the framework. Most migration confusion comes from these:

- **`Group` is a schema, `Container` is the runtime.** In `that-depends`, a `BaseContainer` subclass is *both* the schema and the runtime — you resolve directly from the class. In `modern-di`, `Group` is a namespace-only class (you cannot instantiate it) and you create the runtime `Container(groups=[MyGroup])` separately, typically once at app start. All resolution, overrides, and lifecycle calls go through that `Container` instance.
- **Resolution is sync-only.** `modern-di` does not have `AsyncFactory`, `AsyncSingleton`, or `await container.resolve(...)`. Async work happens in the framework's lifespan — see [§6](#6-async-resources). There is no plan to add async resolution back.
- **Scopes are explicit.** `Scope.APP → SESSION → REQUEST → ACTION → STEP`, with [the scope dependency rule](../providers/scopes.md#the-scope-dependency-rule) enforced at validation time. Framework integrations create the per-request child container automatically.

## 3. Provider mapping

Use this table as the index for the rest of the guide.

| `that-depends` | `modern-di` replacement | Where to look |
|---|---|---|
| `Factory` | `providers.Factory(...)` | [§4](#4-migrate-the-dependency-graph) |
| `Singleton` | `providers.Factory(..., cache=True)` | [§4](#4-migrate-the-dependency-graph) |
| `Resource` (sync gen / ctx mgr) | `providers.Factory(..., cache=CacheSettings(finalizer=...))` | [§4](#4-migrate-the-dependency-graph) |
| `Resource` (async gen / ctx mgr) | Lifespan + `ContextProvider` (or sync creator + async finalizer) | [§6](#6-async-resources) |
| `ContextResource` | `providers.Factory(..., scope=Scope.REQUEST)` | [§5](#5-context-resources-and-request-scope) |
| `AsyncFactory` | Lifespan-managed; expose via `ContextProvider` | [§6](#6-async-resources) |
| `AsyncSingleton` | Lifespan-managed; expose via `ContextProvider` | [§6](#6-async-resources) |
| `Object` | `providers.Factory` with a creator that returns the value | [§4](#4-migrate-the-dependency-graph) |
| `List` | `providers.Factory` with a creator that returns a list | [§4](#4-migrate-the-dependency-graph) |
| `Dict` | `providers.Factory` with a creator that returns a dict | [§4](#4-migrate-the-dependency-graph) |
| `Selector` | No direct equivalent — see [§9](#9-no-direct-equivalent) |
| `AttrGetter` (`provider.attr`) | No direct equivalent — see [§9](#9-no-direct-equivalent) |
| `ThreadLocalSingleton` | No direct equivalent — see [§9](#9-no-direct-equivalent) |
| `State` | `ContextProvider` + `set_context` | [§5](#5-context-resources-and-request-scope) |
| `Provider.bind(Type)` | `providers.Alias(..., bound_type=...)` | [§4](#4-migrate-the-dependency-graph) |
| `@inject` + `Provide[T]()` (web) | `FromDI(T)` from the framework integration | [§8](#8-framework-integration-and-routes) |
| `@inject` + `Provide[T]()` (non-web) | Explicit `container.resolve(T)` | [§9](#9-no-direct-equivalent) |
| `container_context()` | `container.build_child_container(scope=..., context=...)` | [§5](#5-context-resources-and-request-scope) |
| `DIContextMiddleware` | `setup_di(app, container)` / `ModernDIPlugin(container)` | [§8](#8-framework-integration-and-routes) |
| `fetch_context_item` / `_by_type` | `ContextProvider(T)` | [§5](#5-context-resources-and-request-scope) |
| `init_resources()` | Lazy initialization — no equivalent needed | [§7](#7-lifecycle-and-testing) |
| `tear_down()` / `tear_down_sync()` | `await container.close_async()` / `container.close_sync()` | [§7](#7-lifecycle-and-testing) |
| `container.override_providers_sync({...})` | `container.override(provider, mock)` | [§7](#7-lifecycle-and-testing) |
| `provider.override_sync(mock)` | `container.override(provider, mock)` | [§7](#7-lifecycle-and-testing) |

## 4. Migrate the dependency graph

1. Replace `BaseContainer` with `Group`.
2. Add an explicit `scope=` to each provider (defaults to `Scope.APP`).
3. Create the runtime container with `Container(groups=[MyGroup])`. In `modern-di`, the `Group` class is a schema only — you cannot resolve from it directly.

When a provider is passed inside `kwargs={...}`, `modern-di` detects it and resolves it like any other dependency. There is no `.cast` indirection — drop those calls.

=== "that-depends"

      ```python
      from that_depends import BaseContainer, providers

      from app import repositories
      from app.resources.db import create_sa_engine, create_session


      class Dependencies(BaseContainer):
          database_engine = providers.Resource(create_sa_engine, settings=settings.cast)
          session = providers.ContextResource(create_session, engine=database_engine.cast)

          decks_service = providers.Factory(repositories.DecksService, session=session)
          cards_service = providers.Factory(repositories.CardsService, session=session)
      ```

=== "modern-di"

      ```python
      from modern_di import Container, Group, Scope, providers

      from app import repositories
      from app.resources.db import close_sa_engine, close_session, create_sa_engine, create_session


      class Dependencies(Group):
          database_engine = providers.Factory(
              create_sa_engine,
              cache=providers.CacheSettings(finalizer=close_sa_engine),
          )
          session = providers.Factory(
              create_session,
              scope=Scope.REQUEST,
              cache=providers.CacheSettings(finalizer=close_session),
              kwargs={"engine": database_engine},
          )

          decks_service = providers.Factory(
              repositories.DecksService,
              scope=Scope.REQUEST,
              kwargs={"session": session},
          )
          cards_service = providers.Factory(
              repositories.CardsService,
              scope=Scope.REQUEST,
              kwargs={"session": session},
          )


      # Group is a schema. Create the runtime container once at app start.
      container = Container(groups=[Dependencies], validate=True)
      ```

### Per-provider replacements

**`Singleton`** → cached `Factory` of `APP` scope:

```python
# that-depends
some_singleton = providers.Singleton(SomeClass)

# modern-di
some_singleton = providers.Factory(
    SomeClass,
    cache=True,
)
```

**`Resource`** (sync generator or context manager) → cached `Factory` with a `finalizer`, splitting the generator into a creator and a finalizer function — see `database_engine` in the worked example above.

**`Object`** → `Factory` whose creator returns the value. Define a small typed function (lambdas have no return annotation, which prevents resolution by type):

```python
# that-depends
api_key = providers.Object("secret-token")

# modern-di
class ApiKey(str): ...

def _api_key() -> ApiKey:
    return ApiKey("secret-token")

api_key = providers.Factory(_api_key, cache=True)
```

If you only need the value passed into one downstream provider, skip the wrapper and put it directly in that provider's `kwargs`.

**`List` / `Dict`** → `Factory` with a creator that builds the collection:

```python
# that-depends
some_list = providers.List(provider1, provider2)

# modern-di
def build_list(a: SomeType1, b: SomeType2) -> list[object]:
    return [a, b]

some_list = providers.Factory(build_list)
```

**`Provider.bind(Type)`** → `Alias`. Useful when you want an abstract type (`Protocol`, ABC) to resolve to a concrete registered provider:

```python
# that-depends
repo = providers.Factory(PostgresRepository).bind(Repository)

# modern-di
repo = providers.Factory(PostgresRepository, cache=True)
abstract_repo = providers.Alias(PostgresRepository, bound_type=Repository)
```

## 5. Context resources and request scope

The `that-depends` `ContextResource` / `container_context()` / `State` / `fetch_context_item` family all collapse into two `modern-di` mechanisms: `Scope.REQUEST` (and below) providers, and `ContextProvider`. Declaring `scope=Scope.REQUEST` on a provider (e.g. `session` in the worked example above) is enough when a framework integration builds the per-request child container for you; `container_context()`'s manual case maps onto using that same child container as a context manager yourself. See [Building child containers](../providers/scopes.md#building-child-containers) for both forms.

### Injecting custom context (replaces `State`, `fetch_context_item`, `fetch_context_item_by_type`)

Declare a `ContextProvider` for the type you want injected, then supply the instance when you build the child container — or via `set_context` before resolving:

```python
from modern_di import Container, Group, Scope, providers


class TenantId(str): ...


class Dependencies(Group):
    tenant = providers.ContextProvider(TenantId, scope=Scope.REQUEST)

    repo = providers.Factory(
        TenantScopedRepository,                 # signature: (tenant: TenantId, ...)
        scope=Scope.REQUEST,
    )


container = Container(groups=[Dependencies], validate=True)

with container.build_child_container(
    scope=Scope.REQUEST,
    context={TenantId: TenantId("acme")},
) as request_container:
    repo = request_container.resolve(TenantScopedRepository)
```

`ContextProvider` returns the value registered for that type on the container **at the provider's own scope** — there is no global lookup like `fetch_context_item`, and [context never propagates between containers](../providers/context.md#context-propagation). For a REQUEST-scoped `ContextProvider`, pass the value to the request container via `build_child_container(context={TenantId: tenant})` or `request_container.set_context(TenantId, tenant)`.

## 6. Async resources

`modern-di` resolves synchronously. There is no `AsyncFactory`, no `AsyncSingleton`, and no `await container.resolve(...)`. The pattern is **async lives in the lifespan, not in the resolve path.** Three cases cover almost everything.

### Sync creator, async finalizer

The most common shape. `CacheSettings.finalizer` accepts both sync and async functions; `await container.close_async()` (which the framework integrations call automatically at shutdown) awaits the async ones.

```python
import sqlalchemy.ext.asyncio


def create_engine() -> sqlalchemy.ext.asyncio.AsyncEngine:
    return sqlalchemy.ext.asyncio.create_async_engine("postgresql+asyncpg://...")


async def close_engine(engine: sqlalchemy.ext.asyncio.AsyncEngine) -> None:
    await engine.dispose()


engine = providers.Factory(
    create_engine,
    cache=providers.CacheSettings(finalizer=close_engine),
)
```

### Async creator (e.g. `aiohttp.ClientSession`, `await asyncpg.create_pool(...)`)

`that-depends`' async `Resource`, `AsyncFactory`, and `AsyncSingleton` all map onto the same
`modern-di` pattern: do the `await` in the framework's lifespan, then hand the live object to a
`ContextProvider` via `set_context` so downstream factories can depend on its type. See
[Async resources via lifespan](../recipes/async-lifespan.md) for the full pattern, the pitfalls
(setting context before yielding, combining a hand-written lifespan with an integration's
`setup_di`), and which resources construct synchronously enough to skip this and just use a
sync creator with an async finalizer instead.

### Per-request async construction

If a per-request resource genuinely needs `await` at construction time, the simplest path is to make the *creator* sync but have it return a pre-acquired object that you placed into the request container's context. Most cases (SQLAlchemy `AsyncSession`, `httpx.AsyncClient`) can be expressed as sync creator + async finalizer instead — that path is preferred.

## 7. Lifecycle and testing

### Lifecycle

- **No `init_resources()` equivalent** — providers initialize lazily on first resolve; see [Lazy initialization](../providers/lifecycle.md#lazy-initialization) for eager-warmup at startup.
- **`tear_down()` / `tear_down_sync()` → `await container.close_async()` / `container.close_sync()`** (also usable as (async) context managers). The framework integrations call `close_async()` automatically at app shutdown.

### Overrides

Overrides are keyed by **provider reference**, not by name:

```python
# that-depends
container.override_providers_sync({"decks_service": fake_decks_service})

# modern-di
container.override(Dependencies.decks_service, fake_decks_service)
...
container.reset_override(Dependencies.decks_service)  # or reset_override() to clear all
```

See [Testing with overrides](../recipes/testing-overrides.md) for override mechanics (tree-wide sharing, reset). `modern-di-pytest` gives fixture-based wiring in place of hand-written overrides — see [the pytest integration](../integrations/pytest.md).

### Validation

`Container(groups=[...], validate=True)` runs cycle detection and scope-chain checks at startup. Turn it on during migration — it catches missed scope changes and broken dependencies before the first request.

## 8. Framework integration and routes

Replace `DIContextMiddleware` with the integration package's setup call ([FastAPI](../integrations/fastapi.md), [Litestar](../integrations/litestar.md), [FastStream](../integrations/faststream.md), [Typer](../integrations/typer.md)) — it creates per-request child containers, tears them down automatically, and calls `container.close_async()` at shutdown. On routes, `FromDI(T)` replaces both `fastapi.Depends(Provide[T]())` and `litestar.di.Provide`, resolving by type instead of by marker; see the integration pages for the full route examples.

## 9. No direct equivalent

A handful of `that-depends` features have no direct port. Workarounds:

- **`Selector`** — write a creator function that takes whatever the selector depended on and returns the chosen object. If the choice is static (e.g. one implementation per environment), `Alias` may be cleaner.
- **`AttrGetter` (`provider.attr` syntax)** — resolve the parent inside the consuming creator and access the attribute there, or expose a dedicated `Factory` whose creator returns the attribute.
- **`ThreadLocalSingleton`** — use `threading.local()` inside a cached `Factory`'s creator and store the per-thread object there.
- **`@inject` + `Provide[T]()` for non-framework functions** — `modern-di` has no general-purpose injection decorator. Call `container.resolve(T)` explicitly at the call site, or expose the function through a framework integration and use `FromDI(T)`.

## More

- Litestar usage example — [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)
- FastAPI usage example — [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template)
