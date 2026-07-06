# Migration from `dependency-injector`

This guide walks an existing [`dependency-injector`](https://github.com/ets-labs/python-dependency-injector) codebase (~4.9k GitHub stars, the largest Python DI user base) through the move to `modern-di`. Every provider type documented in `dependency-injector`'s [provider catalog](https://python-dependency-injector.ets-labs.org/providers/index.html) has either a mapping below or an explicit note that there is no direct equivalent (with a workaround) — following the same rule as [the `that-depends` migration guide](from-that-depends.md), the in-house template for this page.

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

- **`Group` is a schema, `Container` is the runtime.** `dependency-injector`'s `DeclarativeContainer` subclass is *both* the schema and the runtime — you instantiate it and resolve directly from it. In `modern-di`, `Group` is a namespace-only class (you cannot instantiate it) and you create the runtime `Container(groups=[MyGroup])` separately, typically once at app start. All resolution, overrides, and lifecycle calls go through that `Container` instance.
- **Resolution is by type, not by marker.** `dependency-injector` has [no type-based resolution API](https://python-dependency-injector.ets-labs.org/wiring.html) — every injection point needs an explicit `Provide[Container.some_provider]` marker (or `Annotated[T, Provide[...]]`) plus `container.wire(modules=[...])` to patch it in. `modern-di` resolves by the parameter's type annotation: `container.resolve(SomeType)`, with no marker subsystem and no `wire()` step. See [§6](#6-wiring-replacement) for the failure mode this avoids.
- **Scopes are an explicit, ordered hierarchy.** `dependency-injector` has no scope hierarchy — each provider independently picks a lifetime (`Factory`, `Singleton`, `Resource`, ...), and per-request state is threaded through `Resource` + the `Closing` wiring marker or a second, request-built container. `modern-di` has `Scope.APP → SESSION → REQUEST → ACTION → STEP`: a provider can only depend on providers of equal-or-broader scope, and framework integrations create the per-request child container automatically. See [§7](#7-scopes).

## 3. Provider taxonomy

Use this table as the index for the rest of the guide. Every provider class documented in `dependency-injector`'s live docs is listed; "no direct equivalent" rows link to [§12](#12-no-direct-equivalent) for the workaround.

| `dependency-injector` | `modern-di` replacement | Where to look |
|---|---|---|
| `Factory` | `providers.Factory(...)` | [§4](#4-migrate-the-dependency-graph) |
| `Callable` | `providers.Factory(creator=the_callable)` — `Factory`'s creator can be any callable, not just a class | [§4](#4-migrate-the-dependency-graph) |
| `Singleton` | `providers.Factory(..., cache=True)` | [§4](#4-migrate-the-dependency-graph) |
| `ThreadSafeSingleton` | `providers.Factory(..., cache=True)` — `modern-di`'s cache is lock-guarded by default (`use_lock=True` on the container) | [§4](#4-migrate-the-dependency-graph) |
| `ThreadLocalSingleton` | No direct equivalent — see [§12](#12-no-direct-equivalent) | [§12](#12-no-direct-equivalent) |
| `Resource` (plain-function initializer — their docs' most common form; no shutdown step) | `providers.Factory(..., cache=True)` — same as `Singleton`; add a finalizer only when there is teardown | [§4](#4-migrate-the-dependency-graph) |
| `Resource` (generator / context-manager initializer) | `providers.Factory(..., cache=CacheSettings(finalizer=...))` | [§4](#4-migrate-the-dependency-graph) |
| `Resource` (async initializer) | Lifespan + `ContextProvider` (or sync creator + async finalizer) | [§4](#4-migrate-the-dependency-graph) |
| `ContextLocalResource` | `providers.Factory(scope=Scope.REQUEST, ..., cache=CacheSettings(finalizer=...))` resolved from a per-request child container | [§4](#4-migrate-the-dependency-graph) |
| `Coroutine` | No direct equivalent — resolution is sync-only; do the `await` in the lifespan and inject the result, same as an async `Resource` | [§4](#4-migrate-the-dependency-graph) |
| `Object` | `providers.Factory` with a creator that returns the value | [§4](#4-migrate-the-dependency-graph) |
| `List` | `providers.Factory` with a creator that returns a list | [§4](#4-migrate-the-dependency-graph) |
| `Dict` | `providers.Factory` with a creator that returns a dict | [§4](#4-migrate-the-dependency-graph) |
| `Dependency` | `providers.ContextProvider(context_type=...)` | [§4](#4-migrate-the-dependency-graph) |
| `AbstractFactory` | `providers.Alias(source_type=..., bound_type=...)` — pick the concrete implementation at declaration time instead of via `.override()` before first use | [§4](#4-migrate-the-dependency-graph) |
| `Configuration` | A plain settings object registered as a provider — no config subsystem (`from_yaml`/`from_env`/etc.) | [§5](#5-configuration) |
| `Selector` | No direct equivalent — see [§12](#12-no-direct-equivalent) | [§12](#12-no-direct-equivalent) |
| `Aggregate` / `FactoryAggregate` | No direct equivalent — see [§12](#12-no-direct-equivalent) | [§12](#12-no-direct-equivalent) |
| `.provided` (attribute / item / method-call access on a provider) | No direct equivalent — see [§12](#12-no-direct-equivalent) | [§12](#12-no-direct-equivalent) |
| `@inject` + `Provide[...]` + `container.wire(modules=[...])` (web) | `FromDI(T)` from the framework integration | [§6](#6-wiring-replacement), [§9](#9-routes) |
| `@inject` + `Provide[...]` + `container.wire(modules=[...])` (non-web) | Explicit `container.resolve(T)` | [§6](#6-wiring-replacement) |
| `DeclarativeContainer` | `Group` (schema) + `Container(groups=[...], validate=True)` (runtime) | [§2](#2-key-conceptual-shifts) |
| `container.init_resources()` | Lazy initialization — no equivalent needed | [§10](#10-testing-and-overrides) |
| `container.shutdown_resources()` / `provider.shutdown()` | `container.close_sync()` / `await container.close_async()` | [§10](#10-testing-and-overrides) |
| `provider.override(...)` / `with provider.override(...):` | `container.override(provider, mock)` (no context-manager form yet — see [§10](#10-testing-and-overrides)) | [§10](#10-testing-and-overrides) |
| `provider.reset_override()` / `provider.reset_last_overriding()` | `container.reset_override(provider)` | [§10](#10-testing-and-overrides) |

## 4. Migrate the dependency graph

1. Replace `DeclarativeContainer` with `Group`.
2. Add an explicit `scope=` to each provider (defaults to `Scope.APP`).
3. Create the runtime container with `Container(groups=[MyGroup], validate=True)`. In `modern-di`, `Group` is a schema only — you cannot resolve from it directly, unlike a `DeclarativeContainer` instance.

**`Singleton` / `ThreadSafeSingleton`** → cached `Factory`. There is no separate thread-safe class: `modern-di`'s cache is lock-guarded by default (`Container(..., use_lock=True)`, the default), so the plain `Singleton` and `ThreadSafeSingleton` cases both map to the same thing:

```python
# dependency-injector
some_singleton = providers.Singleton(SomeClass)
some_threadsafe_singleton = providers.ThreadSafeSingleton(SomeClass)

# modern-di
some_singleton = providers.Factory(creator=SomeClass, cache=True)
```

**`Resource`** → cached `Factory`, with or without a `finalizer` depending on the initializer form. Their docs call the plain-function initializer "the most common way to specify resource initialization" — and a plain-function `Resource` has no shutdown step, so it maps to exactly what `Singleton` maps to:

```python
# dependency-injector — plain-function initializer, no shutdown
thread_pool = providers.Resource(init_thread_pool, max_workers=4)

# modern-di — same as the Singleton mapping
thread_pool = providers.Factory(creator=init_thread_pool, kwargs={"max_workers": 4}, cache=True)
```

For the generator or context-manager initializer forms (the ones with a shutdown step), split init and teardown into a plain creator function and a separate finalizer function:

```python
# dependency-injector
def init_resource(argument1=...):
    resource = SomeResource()  # initialization
    yield resource
    # shutdown code

thread_pool = providers.Resource(init_resource)

# modern-di
def create_resource() -> SomeResource:
    return SomeResource()

def close_resource(resource: SomeResource) -> None:
    ...  # shutdown code

thread_pool = providers.Factory(
    creator=create_resource,
    cache=providers.CacheSettings(finalizer=close_resource),
)
```

**`ContextLocalResource`** → `REQUEST`-scoped cached `Factory` with a `finalizer`. `dependency-injector`'s `ContextLocalResource` uses `contextvars` to give each execution context (in practice: each async request) its own instance of a `Resource`, cleaned up when the context ends. `modern-di` expresses the same lifetime explicitly: declare the provider at `Scope.REQUEST` and resolve it from a per-request child container — the framework integrations build that child container for you ([§8](#8-framework-integration)), and closing it runs the finalizer:

```python
# dependency-injector
db_session = providers.ContextLocalResource(AsyncSessionLocal)

# modern-di — one instance per request container, finalizer on request end
db_session = providers.Factory(
    scope=Scope.REQUEST,
    creator=create_session,
    cache=providers.CacheSettings(finalizer=close_session),
)
```

**`Callable`** → a plain `Factory` whose creator is the callable — `modern-di` has no separate "wraps a function vs. wraps a class" distinction; `Factory.creator` accepts any `Callable[..., T]`. Note the call-time argument this example passes (`container.password_hasher("super secret")`) has no `modern-di` equivalent — see the note below:

```python
# dependency-injector
password_hasher = providers.Callable(passlib.hash.sha256_crypt.hash, salt_size=16, rounds=10000)
hashed = container.password_hasher("super secret")  # "super secret" supplied at call time

# modern-di — the value must be static (kwargs) or itself a resolvable dependency
password_hasher = providers.Factory(
    creator=passlib.hash.sha256_crypt.hash,
    kwargs={"secret": "super secret", "salt_size": 16, "rounds": 10000},
)
```

> **Providers are not partially-applied callables in `modern-di`.** In `dependency-injector`, every provider instance is itself callable, and calling it with extra positional/keyword arguments merges them with the declared ones for that one call (`container.some_factory(extra_arg)`). `modern-di`'s `Factory` has no equivalent: `resolve()`/`resolve_provider()` take no arguments, and every constructor argument must be resolvable (by type, by `kwargs`, or by default) at declaration time. If a value genuinely varies per call site, resolve a plain function or make it a `ContextProvider`/`Scope.REQUEST` dependency instead of trying to pass it at the call site.

**`Object`** → `Factory` whose creator returns the value. Define a small typed function (lambdas have no return annotation, which prevents resolution by type):

```python
# dependency-injector
object_provider = providers.Object("secret-token")

# modern-di
class ApiKey(str): ...

def _api_key() -> ApiKey:
    return ApiKey("secret-token")

api_key = providers.Factory(creator=_api_key, cache=True)
```

If you only need the value passed into one downstream provider, skip the wrapper and put it directly in that provider's `kwargs`.

**`List` / `Dict`** → `Factory` with a creator that builds the collection:

```python
# dependency-injector
modules = providers.List(
    providers.Factory(Module, name="m1"),
    providers.Factory(Module, name="m2"),
)

# modern-di
def build_modules() -> list[Module]:
    return [Module("m1"), Module("m2")]

modules = providers.Factory(creator=build_modules)
```

**`Dependency`** → `ContextProvider`. Both are a typed placeholder filled in at runtime rather than constructed by a factory:

```python
# dependency-injector
database = providers.Dependency(instance_of=DbAdapter)
# container = Container(database=providers.Singleton(SqliteDbAdapter))

# modern-di
database = providers.ContextProvider(scope=Scope.APP, context_type=DbAdapter)
# container = Container(groups=[AppGroup], context={DbAdapter: SqliteDbAdapter()})
```

**`AbstractFactory`** → `Alias`. `dependency-injector`'s `AbstractFactory` starts unbound and must be `.override()`-ed with a concrete `Factory` before first use; `modern-di` instead registers the concrete provider directly and re-exports it under the abstract type at declaration time — no override step, and `validate()` catches a missing binding before the first resolve:

```python
# dependency-injector
cache_client_factory = providers.AbstractFactory(AbstractCacheClient)
# container.cache_client_factory.override(providers.Factory(RedisCacheClient, host="localhost"))

# modern-di
redis_cache_client = providers.Factory(creator=RedisCacheClient, cache=True)
cache_client = providers.Alias(source_type=RedisCacheClient, bound_type=AbstractCacheClient)
```

## 5. Configuration

`dependency-injector`'s `Configuration` provider is a subsystem: `providers.Configuration()` plus `.from_yaml()` / `.from_json()` / `.from_ini()` / `.from_env()` / `.from_pydantic()` / `.from_dict()` / `.from_value()` loaders, environment-variable interpolation (`${VAR:default}`), and a "use first, define later" declaration order. `modern-di` deliberately has no equivalent subsystem — this is a design decision, not a gap: load your settings with whatever library you already use (`pydantic-settings`, `environ-config`, plain `os.environ`, ...) into a regular object, then register that object as an ordinary provider:

```python
class Settings:
    def __init__(self) -> None:
        self.database_url = os.environ["DATABASE_URL"]

class AppGroup(Group):
    settings = providers.Factory(creator=Settings, cache=True)
```

If a value needs to be supplied by the caller rather than computed (e.g. it comes from a CLI flag or a request header), use `ContextProvider` instead — see [§4](#4-migrate-the-dependency-graph)'s `Dependency` mapping.

## 6. Wiring replacement

`dependency-injector` requires three cooperating pieces for every injection point: the `@inject` decorator (must be the outermost decorator), a `Provide[Container.provider]` or `Annotated[T, Provide[Container.provider]]` default value, and an explicit `container.wire(modules=[...])` call that patches the marked functions at import time. `modern-di` has no marker subsystem: it resolves by matching a parameter's *type annotation* against the registry, so there is nothing to wire.

```python
# dependency-injector
from dependency_injector.wiring import Provide, inject

@inject
def process(service: Service = Provide[Container.service]) -> None:
    ...

container = Container()
container.wire(modules=[__name__])
```

```python
# modern-di — outside a framework: resolve explicitly at the call site
service = container.resolve(Service)
process(service)
```

```python
# modern-di — inside a web framework: FromDI(T) replaces Provide[Container.x]
from modern_di_fastapi import FromDI

@ROUTER.get("/")
async def handler(service: Service = FromDI(Service)) -> None:
    ...
```

More framework examples in [§8](#8-framework-integration) and [§9](#9-routes).

This also removes `dependency-injector`'s most-filed failure mode: an unwired function's marker is left as a raw `Provide` object, which surfaces as a confusing `AttributeError: 'Provide' object has no attribute ...` deep in your own code ([issue #658](https://github.com/ets-labs/python-dependency-injector/issues/658), [issue #521](https://github.com/ets-labs/python-dependency-injector/issues/521)) rather than a DI-specific error at the point of the mistake. `modern-di` fails at declaration time (`UnsupportedCreatorParameterError`) or resolve time (`ProviderNotRegisteredError`, with "did you mean" suggestions) — see [§11](#11-diagnostics-comparison).

## 7. Scopes

`dependency-injector` has no ordered scope hierarchy. Each provider independently chooses a lifetime class (`Factory` = new object every call, `Singleton`/`ThreadSafeSingleton` = one object per container, `Resource` = one object with init/shutdown hooks), and request-scoped state is either threaded through the `Closing` wiring marker on a `Resource` or built with a second, request-scoped container instantiated per request. `modern-di` has one mechanism for both "create once" and "scoped to a boundary": `Scope.APP → SESSION → REQUEST → ACTION → STEP`, plus child containers.

```python
class AppGroup(Group):
    # one instance for the whole app's lifetime
    db_pool = providers.Factory(scope=Scope.APP, creator=create_pool, cache=True)

    # one instance per request; built by build_child_container(scope=Scope.REQUEST)
    current_user = providers.Factory(scope=Scope.REQUEST, creator=UserFromRequest)

app_container = Container(scope=Scope.APP, groups=[AppGroup], validate=True)
request_container = app_container.build_child_container(scope=Scope.REQUEST, context={...})
```

A provider can only depend on providers of equal-or-broader scope — an `APP`-scoped provider cannot declare a `REQUEST`-scoped constructor parameter. `validate()` catches this (`InvalidScopeDependencyError`) before the first resolve; unvalidated, it surfaces at runtime as `ScopeNotInitializedError` or `ScopeSkippedError` with a breadcrumb naming both the capturing provider and the one that failed. Framework integrations ([§8](#8-framework-integration)) build and tear down the per-request child container automatically, the same role `Resource` + `Closing` (or a hand-rolled second container) plays in `dependency-injector`.

## 8. Framework integration

Replace `container.wire(modules=[...])` (plus any per-framework glue such as `container` attributes on the app object) with the integration package's setup call. The integration creates per-request child containers and tears them down automatically; at app shutdown it calls `container.close_async()` to run finalizers. There is no module list to maintain and no import-time patching.

=== "fastapi"

      ```python
      import fastapi
      import modern_di_fastapi
      from modern_di import Container

      from app.ioc import AppGroup


      container = Container(groups=[AppGroup], validate=True)

      app = fastapi.FastAPI()
      modern_di_fastapi.setup_di(app, container)
      ```

      See [the FastAPI integration docs](../integrations/fastapi.md) for websockets and framework-provided context objects (`fastapi.Request`, `fastapi.WebSocket`).

=== "litestar"

      ```python
      from litestar import Litestar
      import modern_di_litestar
      from modern_di import Container

      from app.ioc import AppGroup


      container = Container(groups=[AppGroup], validate=True)

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

`FromDI(T)` replaces the `@inject` + `Provide[Container.x]` pair on route handlers. Resolution is by type — no marker points at a specific container attribute, and no `@inject` decorator is needed:

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

## 10. Testing and overrides

### Overrides

Overrides are keyed by **provider reference**, not attribute name, same idea as `dependency-injector` but through the container rather than the provider object:

```python
# dependency-injector
container.api_client_factory.override(unittest.mock.Mock(ApiClient))
...
container.api_client_factory.reset_override()

# modern-di
container.override(AppGroup.api_client_factory, unittest.mock.Mock(ApiClient))
...
container.reset_override(AppGroup.api_client_factory)  # or reset_override() to clear all
```

`dependency-injector` also has a context-manager override form (`with container.api_client_factory.override(mock):`) that auto-resets on exit. **`modern-di` does not have this form yet** — `container.override()`/`reset_override()` is imperative-only today; pair the calls manually (e.g. in a pytest fixture's teardown, or `try`/`finally`).

Overrides are shared across the whole container tree: overriding on a parent container is visible to every child, and `close_sync()`/`close_async()` on the *root* container clears all overrides automatically.

### Lifecycle

- **No `init_resources()`.** `modern-di` initializes providers lazily on first resolve; there is no bulk eager-init call. If you need warmup at startup, call `container.resolve(SomeType)` for the providers you want pre-built.
- **`shutdown_resources()` / `provider.shutdown()`** → `container.close_sync()` / `await container.close_async()`, which also work as (async) context managers:

  ```python
  with Container(groups=[AppGroup], validate=True) as container:
      ...  # finalizers run in reverse (LIFO) order on exit
  ```

### Pytest

`modern-di-pytest` provides fixture-based wiring, replacing hand-written `container.override(...)` calls per test:

```python
from modern_di_pytest import expose, modern_di_fixture

# Single fixture, resolved by type or provider
decks_service = modern_di_fixture(DecksService)

# Bulk-generate one fixture per provider in a Group
expose(AppGroup)
```

## 11. Diagnostics comparison

| Failure mode | `dependency-injector` | `modern-di` |
|---|---|---|
| Circular dependency | No cycle detection; a circular provider graph raises a bare `RecursionError` from Cython-level `deepcopy`, with no cycle path ([issue #811](https://github.com/ets-labs/python-dependency-injector/issues/811)) | `validate()` reports every cycle up front as `CircularDependencyError` with an arrow-chain `cycle_path`; even without `validate()`, a runtime cycle hit is caught and re-raised as `CircularDependencyError` (not a bare `RecursionError`) |
| Unwired injection point | Silent: an un-wired function keeps the raw `Provide` marker as its default, surfacing as `AttributeError: 'Provide' object has no attribute ...` far from the actual mistake ([#658](https://github.com/ets-labs/python-dependency-injector/issues/658), [#521](https://github.com/ets-labs/python-dependency-injector/issues/521)) | No marker subsystem to leave unwired: a missing dependency fails at declaration time (`UnsupportedCreatorParameterError`) or resolve time (`ProviderNotRegisteredError`, `ArgumentResolutionError`) |
| Whole-graph validation | None — errors surface one at a time, on first resolve, wherever the graph happens to break | `Container(..., validate=True)` walks the entire graph and raises one `ValidationFailedError` aggregating *every* wiring bug (cycles, inverted scopes, missing dependencies) at once |
| Resolve by type | [No type-based resolution API](https://python-dependency-injector.ets-labs.org/wiring.html) — every call site needs an explicit `Provide[Container.x]` marker | `container.resolve(SomeType)` resolves directly from a type annotation; unregistered types get closest-match ("did you mean") suggestions |

Both diagnostics paths in practice: `validate()` raises `ValidationFailedError` naming the cycle up front; without `validate()`, the same graph's first resolve raises `CircularDependencyError` (not a bare `RecursionError`), though the un-validated path's breadcrumb trail is considerably noisier since the conversion happens deep inside an already near-exhausted call stack — run with `validate=True` during migration to see the clean report instead.

## 12. No direct equivalent

A handful of `dependency-injector` features have no direct port. Workarounds:

- **`ThreadLocalSingleton`** — use `threading.local()` inside a cached `Factory`'s creator and store the per-thread object there.
- **`Selector`** — write a creator function that takes whatever the selector depended on and returns the chosen object. If the choice is static (e.g. one implementation per environment), `Alias` may be cleaner.
- **`Aggregate` / `FactoryAggregate`** — resolve each candidate provider individually (by type or by reference) and dispatch on the key yourself in a small creator function, rather than injecting the whole aggregate object.
- **`.provided` (attribute / item / method-call access on a provider, e.g. `service.provided.value`)** — resolve the parent inside the consuming creator and access the attribute, item, or method result there, or expose a dedicated `Factory` whose creator returns just that piece.
- **`@inject` + `Provide[T]()` for non-framework functions** — `modern-di` has no general-purpose injection decorator. Call `container.resolve(T)` explicitly at the call site, or expose the function through a framework integration and use `FromDI(T)`.
- **Call-time provider arguments** (`container.some_factory(extra_arg)` merging extra args into that one call) — `modern-di` providers resolve with no arguments; move the varying value into `kwargs=` if it is static, or into a `ContextProvider`/deeper-scoped dependency if it genuinely varies per call site.

## More

- [modern-di vs dependency-injector](../introduction/comparison.md#vs-dependency-injector) — the short, non-migration-focused comparison.
- Litestar usage example — [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)
- FastAPI usage example — [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template)
