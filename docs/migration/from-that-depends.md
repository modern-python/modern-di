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
- **Scopes are explicit.** `Scope.APP → SESSION → REQUEST → ACTION → STEP`. A provider can only depend on providers of equal-or-broader scope (a `REQUEST`-scoped provider may depend on `APP`-scoped providers, but not the other way around). Framework integrations create the per-request child container automatically.

## 3. Provider mapping

Use this table as the index for the rest of the guide.

| `that-depends` | `modern-di` replacement | Where to look |
|---|---|---|
| `Factory` | `providers.Factory(...)` | [§4](#4-migrate-the-dependency-graph) |
| `Singleton` | `providers.Factory(..., cache_settings=CacheSettings())` | [§4](#4-migrate-the-dependency-graph) |
| `Resource` (sync gen / ctx mgr) | `providers.Factory(..., cache_settings=CacheSettings(finalizer=...))` | [§4](#4-migrate-the-dependency-graph) |
| `Resource` (async gen / ctx mgr) | Lifespan + `ContextProvider` (or sync creator + async finalizer) | [§6](#6-async-resources) |
| `ContextResource` | `providers.Factory(scope=Scope.REQUEST, ...)` | [§5](#5-context-resources-and-request-scope) |
| `AsyncFactory` | Lifespan-managed; expose via `ContextProvider` | [§6](#6-async-resources) |
| `AsyncSingleton` | Lifespan-managed; expose via `ContextProvider` | [§6](#6-async-resources) |
| `Object` | `providers.Factory` with a creator that returns the value | [§4](#4-migrate-the-dependency-graph) |
| `List` | `providers.Factory` with a creator that returns a list | [§4](#4-migrate-the-dependency-graph) |
| `Dict` | `providers.Factory` with a creator that returns a dict | [§4](#4-migrate-the-dependency-graph) |
| `Selector` | No direct equivalent — see [§10](#10-no-direct-equivalent) |
| `AttrGetter` (`provider.attr`) | No direct equivalent — see [§10](#10-no-direct-equivalent) |
| `ThreadLocalSingleton` | No direct equivalent — see [§10](#10-no-direct-equivalent) |
| `State` | `ContextProvider` + `set_context` | [§5](#5-context-resources-and-request-scope) |
| `Provider.bind(Type)` | `providers.Alias(source_type=..., bound_type=...)` | [§4](#4-migrate-the-dependency-graph) |
| `@inject` + `Provide[T]()` (web) | `FromDI(T)` from the framework integration | [§9](#9-routes) |
| `@inject` + `Provide[T]()` (non-web) | Explicit `container.resolve(T)` | [§10](#10-no-direct-equivalent) |
| `container_context()` | `container.build_child_container(scope=..., context=...)` | [§5](#5-context-resources-and-request-scope) |
| `DIContextMiddleware` | `setup_di(app, container)` / `ModernDIPlugin(container)` | [§8](#8-framework-integration) |
| `fetch_context_item` / `_by_type` | `ContextProvider(context_type=T)` | [§5](#5-context-resources-and-request-scope) |
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
              creator=create_sa_engine,
              cache_settings=providers.CacheSettings(finalizer=close_sa_engine),
          )
          session = providers.Factory(
              scope=Scope.REQUEST,
              creator=create_session,
              cache_settings=providers.CacheSettings(finalizer=close_session),
              kwargs={"engine": database_engine},
          )

          decks_service = providers.Factory(
              scope=Scope.REQUEST,
              creator=repositories.DecksService,
              kwargs={"session": session},
          )
          cards_service = providers.Factory(
              scope=Scope.REQUEST,
              creator=repositories.CardsService,
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
    creator=SomeClass,
    cache_settings=providers.CacheSettings(),
)
```

**`Resource`** (sync generator or context manager) → cached `Factory` with a `finalizer`:

```python
# that-depends
some_resource = providers.Resource(create_resource)  # sync generator

# modern-di — split the generator into a creator and a finalizer
some_resource = providers.Factory(
    creator=create_resource,                # plain function returning the resource
    cache_settings=providers.CacheSettings(finalizer=close_resource),
)
```

**`Object`** → `Factory` whose creator returns the value. Define a small typed function (lambdas have no return annotation, which prevents resolution by type):

```python
# that-depends
api_key = providers.Object("secret-token")

# modern-di
class ApiKey(str): ...

def _api_key() -> ApiKey:
    return ApiKey("secret-token")

api_key = providers.Factory(creator=_api_key, cache_settings=providers.CacheSettings())
```

If you only need the value passed into one downstream provider, skip the wrapper and put it directly in that provider's `kwargs`.

**`List` / `Dict`** → `Factory` with a creator that builds the collection:

```python
# that-depends
some_list = providers.List(provider1, provider2)

# modern-di
def build_list(a: SomeType1, b: SomeType2) -> list[object]:
    return [a, b]

some_list = providers.Factory(creator=build_list)
```

**`Provider.bind(Type)`** → `Alias`. Useful when you want an abstract type (`Protocol`, ABC) to resolve to a concrete registered provider:

```python
# that-depends
repo = providers.Factory(PostgresRepository).bind(Repository)

# modern-di
repo = providers.Factory(creator=PostgresRepository, cache_settings=providers.CacheSettings())
abstract_repo = providers.Alias(source_type=PostgresRepository, bound_type=Repository)
```

## 5. Context resources and request scope

The `that-depends` `ContextResource` / `container_context()` / `State` / `fetch_context_item` family all collapse into two `modern-di` mechanisms: `Scope.REQUEST` (and below) providers, and `ContextProvider`.

### Per-request providers with a framework

The framework integration creates a `REQUEST`-scope child container per request and tears it down at the end (running any registered finalizers). You only need to declare the scope:

```python
session = providers.Factory(
    scope=Scope.REQUEST,
    creator=create_session,
    cache_settings=providers.CacheSettings(finalizer=close_session),
    kwargs={"engine": database_engine},
)
```

### Manual scope management (outside web frameworks)

Replaces `container_context()`. Use the child container as a context manager — exiting it runs finalizers in reverse order:

```python
with container.build_child_container(scope=Scope.REQUEST) as request_container:
    service = request_container.resolve(DecksService)
    ...
# finalizers (e.g. close_session) ran on exit
```

### Injecting custom context (replaces `State`, `fetch_context_item`, `fetch_context_item_by_type`)

Declare a `ContextProvider` for the type you want injected, then supply the instance when you build the child container — or via `set_context` before resolving:

```python
from modern_di import Container, Group, Scope, providers


class TenantId(str): ...


class Dependencies(Group):
    tenant = providers.ContextProvider(scope=Scope.REQUEST, context_type=TenantId)

    repo = providers.Factory(
        scope=Scope.REQUEST,
        creator=TenantScopedRepository,         # signature: (tenant: TenantId, ...)
    )


container = Container(groups=[Dependencies])

with container.build_child_container(
    scope=Scope.REQUEST,
    context={TenantId: TenantId("acme")},
) as request_container:
    repo = request_container.resolve(TenantScopedRepository)
```

`ContextProvider` returns the value registered for that type on the container **at the provider's own scope** — there is no global lookup like `fetch_context_item`. Context never propagates between containers, so build order is irrelevant: setting context on a parent container never reaches a child-scoped provider. For a REQUEST-scoped `ContextProvider`, pass the value to the request container via `build_child_container(context={TenantId: tenant})` or `request_container.set_context(TenantId, tenant)`.

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
    creator=create_engine,
    cache_settings=providers.CacheSettings(finalizer=close_engine),
)
```

### Async creator (e.g. `aiohttp.ClientSession`, `await asyncpg.create_pool(...)`)

Do the async work in the framework's lifespan, then inject the result as context. `set_context` registers the live object so `ContextProvider` (or type-based resolution) can return it:

```python
import contextlib
from collections.abc import AsyncIterator

import aiohttp
import fastapi
from modern_di import Container, Group, Scope, providers


class Dependencies(Group):
    http_client = providers.ContextProvider(scope=Scope.APP, context_type=aiohttp.ClientSession)


container = Container(groups=[Dependencies])


@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI) -> AsyncIterator[None]:
    async with container:                              # runs close_async on exit
        async with aiohttp.ClientSession() as session:  # must be inside running loop
            container.set_context(aiohttp.ClientSession, session)
            yield


app = fastapi.FastAPI(lifespan=lifespan)
```

Downstream factories declare `client: aiohttp.ClientSession` as a parameter and get the live instance via type-based resolution. Use this pattern for `aiohttp.ClientSession`, `asyncpg.create_pool`, or any resource whose constructor genuinely requires `await` or a running event loop. Resources that *look* async but construct synchronously (`redis.asyncio.Redis.from_url`, `sqlalchemy.ext.asyncio.create_async_engine`, `httpx.AsyncClient`) are better expressed as the previous case — sync creator with an async finalizer.

### Per-request async construction

If a per-request resource genuinely needs `await` at construction time, the simplest path is to make the *creator* sync but have it return a pre-acquired object that you placed into the request container's context. Most cases (SQLAlchemy `AsyncSession`, `httpx.AsyncClient`) can be expressed as sync creator + async finalizer instead — that path is preferred.

## 7. Lifecycle and testing

### Lifecycle

- **No `init_resources()`.** `modern-di` initializes providers lazily on first resolve. If you need eager warmup at startup, call `container.resolve(SomeType)` for the providers you want pre-built — typically in the framework's startup hook.
- **`tear_down()` / `tear_down_sync()`** → `await container.close_async()` / `container.close_sync()`. Both also work as (async) context managers:

  ```python
  async with container:
      ...  # finalizers run on exit
  ```

  The framework integrations call `close_async()` automatically at app shutdown.

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

Overrides are shared across the container tree — overriding on the root container affects all child containers.

### Pytest

`modern-di-pytest` provides fixture-based wiring:

```python
from modern_di_pytest import expose, modern_di_fixture

# Single fixture, resolved by type or provider
decks_service = modern_di_fixture(DecksService)

# Bulk-generate one fixture per provider in a Group
expose(Dependencies)
```

### Validation

`Container(groups=[...], validate=True)` runs cycle detection and scope-chain checks at startup. Turn it on during migration — it catches missed scope changes and broken dependencies before the first request.

## 8. Framework integration

Replace `DIContextMiddleware` (`that-depends`) with the integration package's setup call. The integration creates per-request child containers and tears them down automatically; at app shutdown it calls `container.close_async()` to run finalizers.

=== "fastapi"

      ```python
      import fastapi
      import modern_di_fastapi
      from modern_di import Container

      from app.ioc import Dependencies


      container = Container(groups=[Dependencies], validate=True)

      app = fastapi.FastAPI()
      modern_di_fastapi.setup_di(app, container)
      ```

      See [the FastAPI integration docs](../integrations/fastapi.md) for websockets and framework-provided context objects (`fastapi.Request`, `fastapi.WebSocket`).

=== "litestar"

      ```python
      from litestar import Litestar
      import modern_di_litestar
      from modern_di import Container

      from app.ioc import Dependencies


      container = Container(groups=[Dependencies], validate=True)

      app = Litestar(
          route_handlers=[...],
          plugins=[modern_di_litestar.ModernDIPlugin(container)],
      )
      ```

      See [the Litestar integration docs](../integrations/litestar.md) for `autowired_groups` and websockets.

=== "faststream"

      See [the FastStream integration docs](../integrations/faststream.md) for the full setup.

=== "typer"

      See [the Typer integration docs](../integrations/typer.md) for the full setup.

## 9. Routes

`FromDI(T)` replaces both `fastapi.Depends(Provide[T]())` and `litestar.di.Provide`. Resolution is by type — the dependency's return type annotation drives the lookup.

=== "fastapi"

      ```python
      import typing

      import fastapi
      from modern_di_fastapi import FromDI

      from app import schemas
      from app.repositories import DecksService


      ROUTER: typing.Final = fastapi.APIRouter()


      @ROUTER.get("/decks/")
      async def list_decks(
          decks_service: DecksService = FromDI(DecksService),
      ) -> schemas.Decks:
          objects = await decks_service.list()
          return schemas.Decks(items=objects)
      ```

=== "litestar"

      ```python
      import litestar
      from modern_di_litestar import FromDI

      from app import schemas
      from app.repositories import DecksService


      @litestar.get("/decks/", dependencies={
          "decks_service": FromDI(DecksService),
      })
      async def list_decks(decks_service: DecksService) -> schemas.Decks:
          objects = await decks_service.list()
          return schemas.Decks(items=objects)
      ```

## 10. No direct equivalent

A handful of `that-depends` features have no direct port. Workarounds:

- **`Selector`** — write a creator function that takes whatever the selector depended on and returns the chosen object. If the choice is static (e.g. one implementation per environment), `Alias` may be cleaner.
- **`AttrGetter` (`provider.attr` syntax)** — resolve the parent inside the consuming creator and access the attribute there, or expose a dedicated `Factory` whose creator returns the attribute.
- **`ThreadLocalSingleton`** — use `threading.local()` inside a cached `Factory`'s creator and store the per-thread object there.
- **`@inject` + `Provide[T]()` for non-framework functions** — `modern-di` has no general-purpose injection decorator. Call `container.resolve(T)` explicitly at the call site, or expose the function through a framework integration and use `FromDI(T)`.

## More

- LiteStar usage example — [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)
- FastAPI usage example — [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template)
