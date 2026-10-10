# Migration from `that-depends`

This guide walks an existing `that-depends` codebase through the move to `modern-di`. Every provider type and core concept in `that-depends` has either a mapping below or a note that there is no direct equivalent, with a workaround.

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

Framework integrations and the pytest helper live in separate packages. These cover the frameworks `that-depends` integrates with:

=== "uv"

      ```bash
      uv add modern-di-fastapi      # FastAPI
      uv add modern-di-litestar     # Litestar
      uv add modern-di-faststream   # FastStream
      uv add --dev modern-di-pytest # pytest fixtures
      ```

=== "pip"

      ```bash
      pip install modern-di-fastapi
      pip install modern-di-litestar
      pip install modern-di-faststream
      pip install modern-di-pytest
      ```

There are also integrations for [aiohttp](../integrations/aiohttp.md), [Starlette](../integrations/starlette.md), [Flask](../integrations/flask.md), [Celery](../integrations/celery.md), [arq](../integrations/arq.md), [taskiq](../integrations/taskiq.md), [gRPC](../integrations/grpc.md), [aiogram](../integrations/aiogram.md), [FastMCP](../integrations/fastmcp.md) and [Typer](../integrations/typer.md), each installed as `modern-di-<name>`.

## 2. Key conceptual shifts

Three things change in how you think about the framework. Most migration confusion comes from these:

- `Group` is a schema and `Container` is the runtime. In `that-depends`, a `BaseContainer` subclass is *both* the schema and the runtime: you resolve directly from the class. In `modern-di`, `Group` is a namespace-only class (you cannot instantiate it) and you create the runtime `Container(groups=[MyGroup])` separately, typically once at app start. All resolution, overrides, and lifecycle calls go through that `Container` instance.
- Resolution is sync-only. `modern-di` does not have `AsyncFactory`, `AsyncSingleton`, or `await container.resolve(...)`. Async work happens in the framework's lifespan (see [§6](#6-async-resources)), and finalizers may be async. [Design decisions](../introduction/design-decisions.md#1-resolution-is-sync-only-finalizers-may-be-sync-or-async) explains why there are no plans to add async resolution.
- Scopes are ordered. `that-depends` has named scopes (`ContextScopes.APP`, `REQUEST` and so on) that `container_context(scope=...)` enters. `modern-di` scopes form a chain, `Scope.APP → SESSION → REQUEST → ACTION → STEP`, and a provider may depend only on providers of its own or a broader scope. `container.validate()` enforces [the scope dependency rule](../providers/scopes.md#the-scope-dependency-rule). Framework integrations create the per-request child container for you.

## 3. Provider mapping

Use this table as the index for the rest of the guide.

| `that-depends` | `modern-di` replacement | Where to look |
|---|---|---|
| `BaseContainer` | `Group` (schema) + `Container(groups=[...])` (runtime) | [§4](#4-migrate-the-dependency-graph) |
| `BaseContainer.connect_containers(A, B)` | One `Container(groups=[A, B])`; closing it tears down every group | [§4](#4-migrate-the-dependency-graph) |
| `Factory` | `providers.Factory(...)` | [§4](#4-migrate-the-dependency-graph) |
| `Singleton` | `providers.Factory(..., cache=True)` | [§4](#4-migrate-the-dependency-graph) |
| `Resource` (sync gen / ctx mgr) | `providers.Factory(..., cache=CacheSettings(finalizer=...))` | [§4](#4-migrate-the-dependency-graph) |
| `Resource` (async gen / ctx mgr) | Lifespan + `ContextProvider` (or sync creator + async finalizer) | [§6](#6-async-resources) |
| `ContextResource` | `providers.Factory(..., scope=Scope.REQUEST, cache=CacheSettings(finalizer=...))` | [§5](#5-context-resources-and-request-scope) |
| `AsyncFactory` | Lifespan-managed; expose via `ContextProvider` | [§6](#6-async-resources) |
| `AsyncSingleton` | Lifespan-managed; expose via `ContextProvider` | [§6](#6-async-resources) |
| `Object` | `providers.Factory` with a creator that returns the value | [§4](#4-migrate-the-dependency-graph) |
| `List` | `providers.Factory` with a creator that returns a list | [§4](#4-migrate-the-dependency-graph) |
| `Dict` | `providers.Factory` with a creator that returns a dict | [§4](#4-migrate-the-dependency-graph) |
| `Selector` | No direct equivalent | [§9](#9-no-direct-equivalent) |
| `AttrGetter` (`provider.attr`) | No direct equivalent | [§9](#9-no-direct-equivalent) |
| `ThreadLocalSingleton` | No direct equivalent | [§9](#9-no-direct-equivalent) |
| `State` | `ContextProvider` + `set_context` | [§5](#5-context-resources-and-request-scope) |
| `provider.bind(T)` | `providers.Factory(..., bound_type=T)`; add an `Alias` per extra type | [§4](#4-migrate-the-dependency-graph) |
| `ContextScopes` / `default_scope` | `Scope` / `class MyGroup(Group, scope=...)` | [§5](#5-context-resources-and-request-scope) |
| `@inject` + `Provide[Container.x]`, `Provide()` or `Provide["Container.x"]` (web) | `FromDI(T)` from the framework integration | [§8](#8-framework-integration-and-routes) |
| `fastapi.Depends(Container.x)` / `litestar.di.Provide(Container.x)` | `FromDI(T)` from the framework integration | [§8](#8-framework-integration-and-routes) |
| `@inject` + `Provide[...]` (non-web) | Explicit `container.resolve(T)` | [§9](#9-no-direct-equivalent) |
| `experimental.LazyProvider` | Not needed: type-based wiring never imports the provider | [§4](#4-migrate-the-dependency-graph) |
| `BaseContainer.resolve(func)` / `resolver(func)` | Register `func` as a `Factory` and resolve that | [§9](#9-no-direct-equivalent) |
| `container_context()` | `container.build_child_container(scope=..., context=...)` | [§5](#5-context-resources-and-request-scope) |
| `DIContextMiddleware` | The integration's setup call, such as `setup_di(app, container)` or `ModernDIPlugin(container)` | [§8](#8-framework-integration-and-routes) |
| `fetch_context_item` / `_by_type` | `ContextProvider(T)` | [§5](#5-context-resources-and-request-scope) |
| `init_resources()` | Lazy initialization; no equivalent needed | [§7](#7-lifecycle-and-testing) |
| `tear_down()` / `tear_down_sync()` | `await container.close_async()` / `container.close_sync()` | [§7](#7-lifecycle-and-testing) |
| `with Container.override_providers_sync({...}):` | One `with container.override(provider, mock):` per provider | [§7](#7-lifecycle-and-testing) |
| `provider.override_sync(mock)` | `container.override(provider, mock)` | [§7](#7-lifecycle-and-testing) |
| `with provider.override_context_sync(mock):` | `with container.override(provider, mock):` | [§7](#7-lifecycle-and-testing) |

## 4. Migrate the dependency graph

1. Replace `BaseContainer` with `Group`.
2. Give each provider that is not app-wide a `scope=`. A provider without one is `Scope.APP`. For a group whose providers mostly share a scope, set a [group-level default](../providers/scopes.md#group-level-default-scope) with `class Dependencies(Group, scope=Scope.REQUEST)`, the way `default_scope` works in `that-depends`.
3. Create the runtime container with `Container(groups=[MyGroup])`. In `modern-di`, the `Group` class is a schema only; you cannot resolve from it directly. Containers you joined with `connect_containers` become several groups in one `Container`.

A provider passed inside `kwargs={...}` is resolved like any other dependency. There is no `.cast` indirection, so drop those calls. A creator parameter with a type annotation needs no `kwargs` entry at all: `modern-di` wires it to the provider registered for that type. Below, `create_sa_engine(settings: Settings)` gets the cached `Settings` that way, and `session` passes the engine by reference to show the other form.

=== "that-depends"

      ```python
      from that_depends import BaseContainer, providers

      from app import repositories
      from app.resources.db import create_sa_engine, create_session
      from app.settings import Settings


      class Dependencies(BaseContainer):
          settings = providers.Singleton(Settings)
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
      from app.settings import Settings


      class Dependencies(Group):
          settings = providers.Factory(Settings, cache=True)
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


      container = Container(groups=[Dependencies])
      ```

Type-based wiring also replaces `that-depends`' other ways of pointing at a provider. `Provide()` with a bound type, `Provide["Container.provider"]` strings and `experimental.LazyProvider` all exist to reference a provider without importing it. A `modern-di` creator names the type it needs and never imports the provider.

### Per-provider replacements

Replace `Singleton` with a cached `Factory` of `APP` scope:

```python
# that-depends
some_singleton = providers.Singleton(SomeClass)

# modern-di
some_singleton = providers.Factory(
    SomeClass,
    cache=True,
)
```

Replace a sync `Resource` (sync generator or context manager) with a cached `Factory` that has a `finalizer`, splitting the generator into a creator and a finalizer function. See `database_engine` in the worked example above.

Replace `Object` with a `Factory` whose creator returns the value. Define a small typed function, because a lambda has no return annotation and so gets no type to resolve by:

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

Replace `List` and `Dict` with a `Factory` whose creator builds the collection, and pass that provider to its consumers through `kwargs`:

```python
# that-depends
some_list = providers.List(provider1, provider2)

# modern-di
def build_list(a: SomeType1, b: SomeType2) -> list[object]:
    return [a, b]

some_list = providers.Factory(build_list)
consumer = providers.Factory(Consumer, kwargs={"items": some_list})
```

A parameterized return type registers under its bare origin: `build_list` is bound to `list`, not `list[object]`, so `container.resolve(list[object])` raises `ProviderNotRegisteredError`. A consumer parameter annotated `list[X]` cannot be wired by type either, and `Factory(Consumer)` raises `UnsupportedCreatorParameterError` unless `kwargs` supplies it, as above. Two list-returning factories in one container both claim `list` and raise `DuplicateProviderTypeError`; give all but one `bound_type=None` and pass them by reference.

Replace `provider.bind(Repository)` with `bound_type=`. `bind` replaces the provider's bindings, so the provider answers only for `Repository`, and `bound_type` does the same:

```python
# that-depends
repo = providers.Factory(PostgresRepository).bind(Repository)

# modern-di
repo = providers.Factory(PostgresRepository, bound_type=Repository)
```

When the provider must answer for more than one type, as with `.bind(A, B)` or `contravariant=True`, keep it bound to one type and add an `Alias` for each other type:

```python
repo = providers.Factory(PostgresRepository)
as_repository = providers.Alias(PostgresRepository, bound_type=Repository)
as_audit_repository = providers.Alias(PostgresRepository, bound_type=AuditRepository)
```

## 5. Context resources and request scope

The `that-depends` `ContextResource` / `container_context()` / `State` / `fetch_context_item` family all collapse into two `modern-di` mechanisms: `Scope.REQUEST` (and below) providers, and `ContextProvider`.

A `ContextResource` is one instance per context with teardown when the context exits. In `modern-di` that is a cached `Factory` at `Scope.REQUEST` with a finalizer, like `session` in the worked example: each request container builds one instance and runs the finalizer when it closes. When a framework integration builds the per-request child container, declaring the scope is all you do. `container_context()`'s manual case maps onto using that child container as a context manager yourself. See [Building child containers](../providers/scopes.md#building-child-containers) for both forms.

`ContextScopes.APP` and `ContextScopes.REQUEST` map to `Scope.APP` and `Scope.REQUEST`, and `default_scope` maps to a group-level default scope ([§4](#4-migrate-the-dependency-graph)). `ContextScopes.ANY` and `ContextScopes.INJECT` have no direct equivalent. The nearest is a child container you build and close around the call that needs it. For scopes of your own, see [Custom scopes](../providers/scopes.md#custom-scopes).

### Injecting custom context (replaces `State`, `fetch_context_item`, `fetch_context_item_by_type`)

Declare a `ContextProvider` for the type you want injected, then supply the instance when you build the child container, or via `set_context` before resolving:

```python
from modern_di import Container, Group, Scope, providers


class TenantId(str): ...


class Dependencies(Group):
    tenant = providers.ContextProvider(TenantId, scope=Scope.REQUEST)

    repo = providers.Factory(
        TenantScopedRepository,                 # signature: (tenant: TenantId, ...)
        scope=Scope.REQUEST,
    )


container = Container(groups=[Dependencies])

with container.build_child_container(
    scope=Scope.REQUEST,
    context={TenantId: TenantId("acme")},
) as request_container:
    repo = request_container.resolve(TenantScopedRepository)
```

`ContextProvider` returns the value registered for that type on the container at the provider's own scope. There is no global lookup like `fetch_context_item`, and [context never propagates between containers](../providers/context.md#context-propagation). For a REQUEST-scoped `ContextProvider`, pass the value to the request container via `build_child_container(context={TenantId: tenant})` or `request_container.set_context(TenantId, tenant)`.

## 6. Async resources

`modern-di` resolves synchronously. There is no `AsyncFactory`, no `AsyncSingleton`, and no `await container.resolve(...)`. Async work lives in the lifespan, not in the resolve path. Three cases cover almost everything.

!!! warning "An `async def` creator is not rejected"

    `providers.Factory(create_pool)` accepts an `async def` creator. Resolving it returns the
    coroutine object, never awaited, and the only sign is a `RuntimeWarning: coroutine ... was
    never awaited` when that object is garbage-collected. Porting an `AsyncFactory` by swapping the
    class name produces exactly this, so move each async creator to one of the shapes below.

### Sync creator, async finalizer

The most common shape. `CacheSettings.finalizer` accepts both sync and async functions, and `await container.close_async()` awaits the async ones. `close_sync()` cannot run an async finalizer and raises `FinalizerError`.

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
`setup_di`), and which resources construct synchronously enough to skip this and use a
sync creator with an async finalizer instead.

### Per-request async construction

Most per-request resources, such as SQLAlchemy's `AsyncSession` or `httpx.AsyncClient`, construct synchronously, so a sync creator with an async finalizer covers them. When one really needs `await` to construct, do the `await` in a per-request hook or middleware, then put the result on that request's container with `set_context`, for a `ContextProvider` at `Scope.REQUEST`:

```python
class Dependencies(Group):
    connection = providers.ContextProvider(Connection, scope=Scope.REQUEST)
    repo = providers.Factory(Repository, scope=Scope.REQUEST)  # takes connection: Connection


async with container.build_child_container(scope=Scope.REQUEST) as request_container:
    request_container.set_context(Connection, await acquire_connection())
    repo = request_container.resolve(Repository)
```

## 7. Lifecycle and testing

### Lifecycle

- There is no `init_resources()` equivalent: providers initialize lazily on first resolve; see [Lazy initialization](../providers/lifecycle.md#lazy-initialization) for eager-warmup at startup.
- `tear_down()` / `tear_down_sync()` become `await container.close_async()` / `container.close_sync()`, also usable as (async) context managers. Which integrations close the APP container for you is in [§8](#8-framework-integration-and-routes).

### Overrides

Overrides are keyed by provider reference, not by name. `container.override(...)` returns a handle that also works as a context manager and restores the previous state on exit, including on an exception:

```python
# that-depends
with Container.override_providers_sync({"decks_service": fake_decks_service}):
    ...

# modern-di, for one block
with container.override(Dependencies.decks_service, fake_decks_service):
    ...

# modern-di, until reset
container.override(Dependencies.decks_service, fake_decks_service)
...
container.reset_override(Dependencies.decks_service)  # or reset_override() to clear all
```

See [Testing with overrides](../recipes/testing-overrides.md) for override mechanics (tree-wide sharing, reset). `modern-di-pytest` gives fixture-based wiring in place of hand-written overrides; see [the pytest integration](../integrations/pytest.md).

### Validation

Call `container.validate()` at startup during the migration. It walks the whole graph and raises one `ValidationFailedError` listing every problem it finds: cycles, a provider that depends on a narrower scope, creator arguments nothing can supply, and aliases whose source is not registered. It does not check that context values are set; a missing one surfaces at resolve as `ContextValueNotSetError`. With a framework integration, call it after the setup call, which registers the integration's own providers, such as the one for the framework's request object.

## 8. Framework integration and routes

Replace `DIContextMiddleware` with the integration package's setup call, such as `setup_di(app, container)` for [FastAPI](../integrations/fastapi.md) and [FastStream](../integrations/faststream.md) or `ModernDIPlugin(container)` for [Litestar](../integrations/litestar.md). Integrations build a child container for each request or message and close it when the request ends. Most also close the APP container at shutdown. Flask, gRPC and Typer leave the APP container to you, and Typer builds its per-command container in `@modern_di_typer.inject`, not in its setup call; see [Closing the container](../providers/lifecycle.md#closing-the-container). Each integration page says which applies.

On routes, `FromDI(T)` replaces both `fastapi.Depends(Container.provider)` and `litestar.di.Provide(Container.provider)`, resolving by type instead of by provider reference; see the integration pages for the full route examples.

## 9. No direct equivalent

A handful of `that-depends` features have no direct port. Workarounds:

- For `Selector`, write a creator function that takes whatever the selector depended on and returns the chosen object. If the choice is static (e.g. one implementation per environment), `Alias` may be cleaner.
- For `AttrGetter` (`provider.attr` syntax), resolve the parent inside the consuming creator and access the attribute there, or expose a dedicated `Factory` whose creator returns the attribute.
- For `ThreadLocalSingleton`, register an uncached `Factory` whose creator reads the object from a module-level `threading.local()` and creates and stores it there on a thread's first call. A cached `Factory` can't do this, because it caches one object for the whole container.
- `modern-di` has no general-purpose injection decorator to replace `@inject` + `Provide[...]` on non-framework functions. Call `container.resolve(T)` explicitly at the call site, or expose the function through a framework integration and use `FromDI(T)`.
- For `BaseContainer.resolve(func)` and `resolver(func)`, which call `func` with its parameters filled by name, register `func` as a `Factory` with `bound_type=None` and call `container.resolve_provider(...)` on it. Its parameters are then wired by type, not by name.

## More

- Litestar usage example: [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)
- FastAPI usage example: [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template)
