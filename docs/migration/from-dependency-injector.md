# Migration from `dependency-injector`

This guide walks an existing [`dependency-injector`](https://github.com/ets-labs/python-dependency-injector) codebase through the move to `modern-di`. Every provider class you declare in `dependency-injector` 4.x (checked against 4.49.1) has either a mapping below or a note that there is no direct equivalent, with a workaround. The base classes, and the helper classes behind `.provided` and `Configuration`, are covered by those rows. The [provider catalog](https://python-dependency-injector.ets-labs.org/providers/index.html) describes what each one does. [The `that-depends` migration guide](from-that-depends.md) follows the same layout.

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

Each framework integration, and the pytest helper, is a separate package named `modern-di-<name>`. Install the ones you need:

=== "uv"

      ```bash
      uv add modern-di-flask        # Flask
      uv add modern-di-aiohttp      # aiohttp
      uv add modern-di-fastapi      # FastAPI
      uv add --dev modern-di-pytest # pytest fixtures
      ```

=== "pip"

      ```bash
      pip install modern-di-flask
      pip install modern-di-aiohttp
      pip install modern-di-fastapi
      pip install modern-di-pytest
      ```

The full list: [aiogram](../integrations/aiogram.md), [aiohttp](../integrations/aiohttp.md), [arq](../integrations/arq.md), [Celery](../integrations/celery.md), [FastAPI](../integrations/fastapi.md), [FastMCP](../integrations/fastmcp.md), [FastStream](../integrations/faststream.md), [Flask](../integrations/flask.md), [gRPC](../integrations/grpc.md), [Litestar](../integrations/litestar.md), [Starlette](../integrations/starlette.md), [taskiq](../integrations/taskiq.md) and [Typer](../integrations/typer.md).

## 2. Key conceptual shifts

Three things change in how you think about the framework. Most migration confusion comes from these:

- `Group` is a schema and `Container` is the runtime. `dependency-injector`'s `DeclarativeContainer` subclass is *both* the schema and the runtime: you instantiate it and resolve directly from it. In `modern-di`, `Group` is a namespace-only class (you cannot instantiate it) and you create the runtime `Container(groups=[MyGroup])` separately, typically once at app start. All resolution, overrides, and lifecycle calls go through that `Container` instance.
- Resolution is by type, not by marker. `dependency-injector` has [no type-based resolution API](https://python-dependency-injector.ets-labs.org/wiring.html), so every injection point needs an explicit `Provide[Container.some_provider]` marker (or `Annotated[T, Provide[...]]`) plus `container.wire(modules=[...])` to patch it in. `modern-di` resolves by the parameter's type annotation: `container.resolve(SomeType)`, with no marker subsystem and no `wire()` step. See [§6](#6-wiring-replacement) for the failure mode this avoids.
- Scopes are an explicit, ordered hierarchy. `dependency-injector` has no scope hierarchy: each provider independently picks a lifetime (`Factory`, `Singleton`, `Resource`, ...), and per-request state is threaded through `Resource` + the `Closing` wiring marker or a second, request-built container. `modern-di` has `Scope.APP → SESSION → REQUEST → ACTION → STEP`: a provider can only depend on providers of equal-or-broader scope, and framework integrations create the per-request child container automatically. See [§7](#7-scopes).

## 3. Provider taxonomy

Use this table as the index for the rest of the guide. "No direct equivalent" rows link to [§11](#11-no-direct-equivalent) for the workaround.

| `dependency-injector` | `modern-di` replacement | Where to look |
|---|---|---|
| `Factory` | `providers.Factory(...)` | [§4](#4-migrate-the-dependency-graph) |
| `Callable` | `providers.Factory(the_callable)`; `Factory`'s creator can be any callable, not just a class | [§4](#4-migrate-the-dependency-graph) |
| `Singleton` | `providers.Factory(..., cache=True)` | [§4](#4-migrate-the-dependency-graph) |
| `ThreadSafeSingleton` | `providers.Factory(..., cache=True)`; `modern-di`'s cache is always lock-guarded | [§4](#4-migrate-the-dependency-graph) |
| `ThreadLocalSingleton` | No direct equivalent | [§11](#11-no-direct-equivalent) |
| `ContextLocalSingleton` | `providers.Factory(..., scope=Scope.REQUEST, cache=True)` resolved from a per-request child container | [§4](#4-migrate-the-dependency-graph) |
| `Resource` (plain-function initializer, their docs' most common form; no shutdown step) | `providers.Factory(..., cache=True)`, same as `Singleton`; add a finalizer only when there is teardown | [§4](#4-migrate-the-dependency-graph) |
| `Resource` (generator / context-manager initializer) | `providers.Factory(..., cache=CacheSettings(finalizer=...))` | [§4](#4-migrate-the-dependency-graph) |
| `Resource` (async initializer) | Lifespan + `ContextProvider` (or sync creator + async finalizer) | [Async resources via lifespan](../recipes/async-lifespan.md) |
| `ContextLocalResource` | `providers.Factory(..., scope=Scope.REQUEST, cache=CacheSettings(finalizer=...))` resolved from a per-request child container | [§4](#4-migrate-the-dependency-graph) |
| `Coroutine` / `AbstractCoroutine` | No direct equivalent. Resolution is sync-only, so do the `await` in the lifespan and inject the result, same as an async `Resource` | [Async resources via lifespan](../recipes/async-lifespan.md) |
| `Object` | `providers.Factory` with a creator that returns the value | [§4](#4-migrate-the-dependency-graph) |
| `List` | `providers.Factory` with a creator that returns a list | [§4](#4-migrate-the-dependency-graph) |
| `Dict` | `providers.Factory` with a creator that returns a dict | [§4](#4-migrate-the-dependency-graph) |
| `Dependency` / `ExternalDependency` | `providers.ContextProvider(...)` | [§4](#4-migrate-the-dependency-graph) |
| `AbstractFactory` / `AbstractSingleton` / `AbstractCallable` | `providers.Alias(..., bound_type=...)`; pick the concrete implementation at declaration time instead of via `.override()` before first use | [§4](#4-migrate-the-dependency-graph) |
| `Configuration` | A plain settings object registered as a provider; there is no config subsystem (`from_yaml`/`from_env`/etc.) | [§5](#5-configuration) |
| `Container` (a nested container) / `DependenciesContainer` | Pass every `Group` to one `Container(groups=[...])`; providers in one group depend on another group's by type | [§4](#4-migrate-the-dependency-graph) |
| `Self` | A creator parameter annotated `Container` | [§4](#4-migrate-the-dependency-graph) |
| `Delegate` and the `Delegated*` providers (`DelegatedFactory`, `DelegatedSingleton`, ...) | A creator parameter annotated `Container`, resolving the provider later | [§4](#4-migrate-the-dependency-graph) |
| `Selector` | No direct equivalent | [§11](#11-no-direct-equivalent) |
| `Aggregate` / `FactoryAggregate` | No direct equivalent | [§11](#11-no-direct-equivalent) |
| `.provided` (attribute / item / method-call access on a provider) | No direct equivalent | [§11](#11-no-direct-equivalent) |
| `@inject` + `Provide[...]` + `container.wire(modules=[...])` (web) | `FromDI(T)` from the framework integration | [§6](#6-wiring-replacement), [§8](#8-framework-integration-and-routes) |
| `@inject` + `Provide[...]` + `container.wire(modules=[...])` (non-web) | Explicit `container.resolve(T)` | [§6](#6-wiring-replacement) |
| `DeclarativeContainer` | `Group` (schema) + `Container(groups=[...])` (runtime), checked with `.validate()` | [§2](#2-key-conceptual-shifts) |
| `container.init_resources()` | Lazy initialization; no equivalent needed | [§9](#9-testing-and-overrides) |
| `container.shutdown_resources()` / `provider.shutdown()` | `container.close_sync()` / `await container.close_async()` | [§9](#9-testing-and-overrides) |
| `provider.override(...)` / `with provider.override(...):` | `container.override(provider, mock)` / `with container.override(provider, mock):` | [§9](#9-testing-and-overrides) |
| `provider.reset_override()` / `provider.reset_last_overriding()` | `container.reset_override(provider)` | [§9](#9-testing-and-overrides) |

## 4. Migrate the dependency graph

1. Replace `DeclarativeContainer` with `Group`.
2. Give each provider that is not app-wide a `scope=`. A provider without one is `Scope.APP`. A group whose providers mostly share a scope can set a [group-level default](../providers/scopes.md#group-level-default-scope) with `class RequestGroup(Group, scope=Scope.REQUEST)`.
3. Create the runtime container with `Container(groups=[MyGroup])`, then call `container.validate()` for whole-graph checks. In `modern-di`, `Group` is a schema only; you cannot resolve from it directly, unlike a `DeclarativeContainer` instance.

Nested containers and `DependenciesContainer` go away. Declare each part of the graph as its own `Group` and pass them all to one `Container(groups=[CoreGroup, BillingGroup])`. A provider in one group that needs a provider from another names its type as a creator parameter, so neither group refers to the other.

Replace `Singleton` and `ThreadSafeSingleton` with `providers.Factory(SomeClass, cache=True)`. There is no separate thread-safe class, since `modern-di`'s cache is always lock-guarded. See [Cached factories](../providers/factories.md#cached-factories).

Replace `Resource` with a cached `Factory`, with or without a `finalizer` depending on the initializer form. Their docs call the plain-function initializer "the most common way to specify resource initialization", and a plain-function `Resource` has no shutdown step, so it maps to exactly what `Singleton` maps to:

```python
# dependency-injector — plain-function initializer, no shutdown
thread_pool = providers.Resource(init_thread_pool, max_workers=4)

# modern-di — same as the Singleton mapping
thread_pool = providers.Factory(init_thread_pool, kwargs={"max_workers": 4}, cache=True)
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
    create_resource,
    cache=providers.CacheSettings(finalizer=close_resource),
)
```

Replace `ContextLocalResource` with a `REQUEST`-scoped cached `Factory` that has a `finalizer`. `dependency-injector`'s `ContextLocalResource` uses `contextvars` to give each execution context (in practice: each async request) its own instance of a `Resource`, cleaned up when the context ends. `modern-di` expresses the same lifetime explicitly: declare the provider at `Scope.REQUEST` and resolve it from a per-request child container. The framework integrations build that child container for you ([§8](#8-framework-integration-and-routes)), and closing it runs the finalizer:

```python
# dependency-injector
db_session = providers.ContextLocalResource(AsyncSessionLocal)

# modern-di — one instance per request container, finalizer on request end
db_session = providers.Factory(
    create_session,
    scope=Scope.REQUEST,
    cache=providers.CacheSettings(finalizer=close_session),
)
```

`ContextLocalSingleton` is the same lifetime without teardown: `providers.Factory(SomeClass, scope=Scope.REQUEST, cache=True)`.

Replace `Callable` with a plain `Factory` whose creator is the callable. `modern-di` makes no distinction between wrapping a function and wrapping a class: `Factory`'s creator argument accepts any callable. The value a `dependency-injector` caller passes at call time (`"super secret"` below) has to become a static `kwargs` entry or a resolvable dependency; [§11](#11-no-direct-equivalent) covers values that vary per call:

```python
# dependency-injector
password_hasher = providers.Callable(passlib.hash.sha256_crypt.hash, salt_size=16, rounds=10000)
hashed = container.password_hasher("super secret")  # "super secret" supplied at call time

# modern-di — the value must be static (kwargs) or itself a resolvable dependency
password_hasher = providers.Factory(
    passlib.hash.sha256_crypt.hash,
    kwargs={"secret": "super secret", "salt_size": 16, "rounds": 10000},
)
```

Replace `Object` with a `Factory` whose creator returns the value. Define a small typed function, because a lambda has no return annotation and so gets no type to resolve by:

```python
# dependency-injector
object_provider = providers.Object("secret-token")

# modern-di
class ApiKey(str): ...

def _api_key() -> ApiKey:
    return ApiKey("secret-token")

api_key = providers.Factory(_api_key, cache=True)
```

If you only need the value passed into one downstream provider, skip the wrapper and put it directly in that provider's `kwargs`.

Replace `List` and `Dict` with a `Factory` whose creator builds the collection, and pass that provider to its consumers through `kwargs`:

```python
# dependency-injector
modules = providers.List(
    providers.Factory(Module, name="m1"),
    providers.Factory(Module, name="m2"),
)

# modern-di
def build_modules() -> list[Module]:
    return [Module("m1"), Module("m2")]

modules = providers.Factory(build_modules)
registry = providers.Factory(ModuleRegistry, kwargs={"modules": modules})
```

A parameterized return type registers under its bare origin: `build_modules` is bound to `list`, not `list[Module]`, so `container.resolve(list[Module])` raises `ProviderNotRegisteredError`. A consumer parameter annotated `list[Module]` cannot be wired by type either, and `Factory(ModuleRegistry)` raises `UnsupportedCreatorParameterError` unless `kwargs` supplies it, as above. Two list-returning factories in one container both claim `list` and raise `DuplicateProviderTypeError`; give all but one `bound_type=None` and pass them by reference.

Replace `Dependency` with `ContextProvider`. Both are a typed placeholder filled in at runtime rather than constructed by a factory:

```python
# dependency-injector
database = providers.Dependency(instance_of=DbAdapter)
# container = Container(database=providers.Singleton(SqliteDbAdapter))

# modern-di
database = providers.ContextProvider(DbAdapter, scope=Scope.APP)
# container = Container(groups=[AppGroup], context={DbAdapter: SqliteDbAdapter()})
```

`validate()` does not check that a context value is set. Where calling an unset `Dependency` raises at that call, a `ContextProvider` with no value passes validation and raises `ContextValueNotSetError` when something resolves it. Give it `default=` if the value may be absent.

Replace `AbstractFactory` with `Alias`. `dependency-injector`'s `AbstractFactory` starts unbound and must be `.override()`-ed with a concrete `Factory` before first use; `modern-di` instead registers the concrete provider directly and re-exports it under the abstract type at declaration time. There is no override step, and `validate()` reports an alias whose source is not registered before the first resolve. `AbstractSingleton` and `AbstractCallable` map the same way, with `cache=True` on the concrete `Factory` for a singleton:

```python
# dependency-injector
cache_client_factory = providers.AbstractFactory(AbstractCacheClient)
# container.cache_client_factory.override(providers.Factory(RedisCacheClient, host="localhost"))

# modern-di
redis_cache_client = providers.Factory(RedisCacheClient, cache=True)
cache_client = providers.Alias(RedisCacheClient, bound_type=AbstractCacheClient)
```

`Self`, `Delegate` and the `Delegated*` providers exist to hand a creator the container or a provider instead of a built object. In `modern-di`, a creator parameter annotated `Container` receives the container, and the creator resolves what it needs from it when it needs it. The container it gets is the one at the provider's own scope. See [Injecting the container itself](../providers/container.md#injecting-the-container-itself). A dependency resolved that way is hidden from `validate()`, so keep it for code that really needs the container, such as building a child container.

## 5. Configuration

`dependency-injector`'s `Configuration` provider is a subsystem: `providers.Configuration()` plus `.from_yaml()` / `.from_json()` / `.from_ini()` / `.from_env()` / `.from_pydantic()` / `.from_dict()` / `.from_value()` loaders, environment-variable interpolation (`${VAR:default}`), and a "use first, define later" declaration order. `modern-di` deliberately has no equivalent subsystem. Load your settings with whatever library you already use (`pydantic-settings`, `environ-config`, plain `os.environ`, ...) into a regular object, then register that object as an ordinary provider:

```python
class Settings:
    def __init__(self) -> None:
        self.database_url = os.environ["DATABASE_URL"]

class AppGroup(Group):
    settings = providers.Factory(Settings, cache=True)
```

If a value needs to be supplied by the caller rather than computed (e.g. it comes from a CLI flag or a request header), use `ContextProvider` instead; see [§4](#4-migrate-the-dependency-graph)'s `Dependency` mapping.

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

More framework examples in [§8](#8-framework-integration-and-routes).

This also removes `dependency-injector`'s most-filed failure mode: an unwired function's marker is left as a raw `Provide` object, which surfaces as a confusing `AttributeError: 'Provide' object has no attribute ...` deep in your own code ([issue #658](https://github.com/ets-labs/python-dependency-injector/issues/658), [issue #521](https://github.com/ets-labs/python-dependency-injector/issues/521)) rather than a DI-specific error at the point of the mistake. In `modern-di` a missing dependency fails in `validate()`, or on the first resolve that needs it, with `ArgumentResolutionError` for a creator argument nothing can supply or `ProviderNotRegisteredError` for a type you resolve directly. When a type with a similar name is registered, the `ProviderNotRegisteredError` message suggests it. See [§10](#10-diagnostics-comparison).

## 7. Scopes

`dependency-injector` has no ordered scope hierarchy. Each provider independently chooses a lifetime class (`Factory` = new object every call, `Singleton`/`ThreadSafeSingleton` = one object per container, `Resource` = one object with init/shutdown hooks), and request-scoped state is either threaded through the `Closing` wiring marker on a `Resource` or built with a second, request-scoped container instantiated per request. `modern-di` has one mechanism for both "create once" and "scoped to a boundary": `Scope.APP → SESSION → REQUEST → ACTION → STEP`, plus child containers.

```python
class AppGroup(Group):
    # one instance for the whole app's lifetime
    db_pool = providers.Factory(create_pool, scope=Scope.APP, cache=True)

    # one instance per request; built by build_child_container(scope=Scope.REQUEST)
    current_user = providers.Factory(UserFromRequest, scope=Scope.REQUEST)

app_container = Container(scope=Scope.APP, groups=[AppGroup])
request_container = app_container.build_child_container(scope=Scope.REQUEST, context={...})
```

See [the scope dependency rule](../providers/scopes.md#the-scope-dependency-rule) for the equal-or-broader constraint and how `validate()` catches a violation before the first resolve. Framework integrations ([§8](#8-framework-integration-and-routes)) build and tear down the per-request child container automatically, the same role `Resource` + `Closing` (or a hand-rolled second container) plays in `dependency-injector`.

## 8. Framework integration and routes

Replace `container.wire(modules=[...])` (plus any per-framework glue such as `container` attributes on the app object) with the integration package's setup call, such as `setup_di(app, container)` for [Flask](../integrations/flask.md), [aiohttp](../integrations/aiohttp.md) or [FastAPI](../integrations/fastapi.md). There is no module list to maintain and no import-time patching. Integrations build a child container for each request or message and close it when the request ends. Most also close the APP container at shutdown. Flask, gRPC and Typer leave the APP container to you, and Typer builds its per-command container in `@modern_di_typer.inject`, not in its setup call; see [Closing the container](../providers/lifecycle.md#closing-the-container). Each integration page says which applies.

On routes, `FromDI(T)` replaces the `@inject` + `Provide[Container.x]` pair: resolution is by type, so no marker points at a specific container attribute and no `@inject` decorator is needed. See the integration pages for the full route examples.

## 9. Testing and overrides

### Overrides

Overrides are keyed by provider reference, not attribute name, same idea as `dependency-injector` but through the container rather than the provider object:

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

`dependency-injector` also has a context-manager override form (`with container.api_client_factory.override(mock):`) that auto-resets on exit. `modern-di` has the same shape: `with container.override(provider, mock) as m:` applies the override for the block and restores the prior state on exit, including on exception:

```python
# modern-di
with container.override(AppGroup.api_client_factory, unittest.mock.Mock(ApiClient)) as mock_factory:
    ...
```

See [Testing with overrides](../recipes/testing-overrides.md) for tree-wide sharing, nesting, and reset mechanics.

### Lifecycle

- There is no `init_resources()` equivalent: providers initialize lazily on first resolve; see [Lazy initialization](../providers/lifecycle.md#lazy-initialization) for eager-warmup at startup.
- `shutdown_resources()` / `provider.shutdown()` become `container.close_sync()` / `await container.close_async()`, also usable as (async) context managers, with finalizers running in reverse order on exit.

### Pytest

`modern-di-pytest` provides fixture-based wiring, replacing hand-written `container.override(...)` calls per test; see [the pytest integration](../integrations/pytest.md).

## 10. Diagnostics comparison

| Failure mode | `dependency-injector` | `modern-di` |
|---|---|---|
| Circular dependency | No cycle detection; the first call into the cycle raises a bare `RecursionError` with no cycle path ([issue #811](https://github.com/ets-labs/python-dependency-injector/issues/811)) | `validate()` reports every cycle up front as `CircularDependencyError` with an arrow-chain `cycle_path`; without `validate()`, a runtime cycle is caught once the recursion limit is hit and re-raised as `CircularDependencyError`, chained to the `RecursionError` |
| Unwired injection point | Silent: an un-wired function keeps the raw `Provide` marker as its default, surfacing as `AttributeError: 'Provide' object has no attribute ...` far from the actual mistake ([#658](https://github.com/ets-labs/python-dependency-injector/issues/658), [#521](https://github.com/ets-labs/python-dependency-injector/issues/521)) | No marker subsystem to leave unwired: a missing dependency fails in `validate()` or on the first resolve that needs it (`ArgumentResolutionError`, `ProviderNotRegisteredError`) |
| Whole-graph validation | None: errors surface one at a time, on first resolve, wherever the graph happens to break | `container.validate()` walks the entire graph and raises one `ValidationFailedError` aggregating *every* wiring bug (cycles, inverted scopes, missing dependencies) at once |
| Resolve by type | [No type-based resolution API](https://python-dependency-injector.ets-labs.org/wiring.html); every call site needs an explicit `Provide[Container.x]` marker | `container.resolve(SomeType)` resolves directly from a type annotation; for an unregistered type, the error suggests registered types with a similar name |

Call `container.validate()` at startup during the migration. Without it, a cycle is found only after the resolve hits the recursion limit, so the `CircularDependencyError` arrives chained to a `RecursionError` traceback thousands of lines long.

## 11. No direct equivalent

A handful of `dependency-injector` features have no direct port. Workarounds:

- For `ThreadLocalSingleton`, register an uncached `Factory` whose creator reads the object from a module-level `threading.local()` and creates and stores it there on a thread's first call. A cached `Factory` can't do this, because it caches one object for the whole container.
- For `Selector`, write a creator function that takes whatever the selector depended on and returns the chosen object. If the choice is static (e.g. one implementation per environment), `Alias` may be cleaner.
- For `Aggregate` / `FactoryAggregate`, resolve each candidate provider individually (by type or by reference) and dispatch on the key yourself in a small creator function, rather than injecting the whole aggregate object.
- For `.provided` (attribute / item / method-call access on a provider, e.g. `service.provided.value`), resolve the parent inside the consuming creator and access the attribute, item, or method result there, or expose a dedicated `Factory` whose creator returns just that piece.
- `modern-di` has no general-purpose injection decorator to replace `@inject` + `Provide[...]` on non-framework functions. Call `container.resolve(T)` explicitly at the call site, or expose the function through a framework integration and use `FromDI(T)`.
- Providers are not partially applied callables. In `dependency-injector`, calling a provider with extra arguments (`container.some_factory(extra_arg)`) merges them with the declared ones for that one call. `modern-di`'s `resolve()` and `resolve_provider()` take no arguments, so every creator argument must come from its type, from `kwargs`, or from a default. Move a static value into `kwargs=`. For a value that varies per call site, use a `ContextProvider` set on the container you resolve from, or a deeper-scoped dependency.

## More

- [modern-di vs dependency-injector](../introduction/comparison.md#vs-dependency-injector): the short, non-migration-focused comparison.
- Litestar usage example: [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)
- FastAPI usage example: [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template)
