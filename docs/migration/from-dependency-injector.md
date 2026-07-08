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

Use this table as the index for the rest of the guide. Every provider class documented in `dependency-injector`'s live docs is listed; "no direct equivalent" rows link to [§11](#11-no-direct-equivalent) for the workaround.

| `dependency-injector` | `modern-di` replacement | Where to look |
|---|---|---|
| `Factory` | `providers.Factory(...)` | [§4](#4-migrate-the-dependency-graph) |
| `Callable` | `providers.Factory(the_callable)` — `Factory`'s creator can be any callable, not just a class | [§4](#4-migrate-the-dependency-graph) |
| `Singleton` | `providers.Factory(..., cache=True)` | [§4](#4-migrate-the-dependency-graph) |
| `ThreadSafeSingleton` | `providers.Factory(..., cache=True)` — `modern-di`'s cache is lock-guarded by default (`use_lock=True` on the container) | [§4](#4-migrate-the-dependency-graph) |
| `ThreadLocalSingleton` | No direct equivalent — see [§11](#11-no-direct-equivalent) | [§11](#11-no-direct-equivalent) |
| `Resource` (plain-function initializer — their docs' most common form; no shutdown step) | `providers.Factory(..., cache=True)` — same as `Singleton`; add a finalizer only when there is teardown | [§4](#4-migrate-the-dependency-graph) |
| `Resource` (generator / context-manager initializer) | `providers.Factory(..., cache=CacheSettings(finalizer=...))` | [§4](#4-migrate-the-dependency-graph) |
| `Resource` (async initializer) | Lifespan + `ContextProvider` (or sync creator + async finalizer) | [§4](#4-migrate-the-dependency-graph) |
| `ContextLocalResource` | `providers.Factory(..., scope=Scope.REQUEST, cache=CacheSettings(finalizer=...))` resolved from a per-request child container | [§4](#4-migrate-the-dependency-graph) |
| `Coroutine` | No direct equivalent — resolution is sync-only; do the `await` in the lifespan and inject the result, same as an async `Resource` | [§4](#4-migrate-the-dependency-graph) |
| `Object` | `providers.Factory` with a creator that returns the value | [§4](#4-migrate-the-dependency-graph) |
| `List` | `providers.Factory` with a creator that returns a list | [§4](#4-migrate-the-dependency-graph) |
| `Dict` | `providers.Factory` with a creator that returns a dict | [§4](#4-migrate-the-dependency-graph) |
| `Dependency` | `providers.ContextProvider(...)` | [§4](#4-migrate-the-dependency-graph) |
| `AbstractFactory` | `providers.Alias(..., bound_type=...)` — pick the concrete implementation at declaration time instead of via `.override()` before first use | [§4](#4-migrate-the-dependency-graph) |
| `Configuration` | A plain settings object registered as a provider — no config subsystem (`from_yaml`/`from_env`/etc.) | [§5](#5-configuration) |
| `Selector` | No direct equivalent — see [§11](#11-no-direct-equivalent) | [§11](#11-no-direct-equivalent) |
| `Aggregate` / `FactoryAggregate` | No direct equivalent — see [§11](#11-no-direct-equivalent) | [§11](#11-no-direct-equivalent) |
| `.provided` (attribute / item / method-call access on a provider) | No direct equivalent — see [§11](#11-no-direct-equivalent) | [§11](#11-no-direct-equivalent) |
| `@inject` + `Provide[...]` + `container.wire(modules=[...])` (web) | `FromDI(T)` from the framework integration | [§6](#6-wiring-replacement), [§8](#8-framework-integration-and-routes) |
| `@inject` + `Provide[...]` + `container.wire(modules=[...])` (non-web) | Explicit `container.resolve(T)` | [§6](#6-wiring-replacement) |
| `DeclarativeContainer` | `Group` (schema) + `Container(groups=[...], validate=True)` (runtime) | [§2](#2-key-conceptual-shifts) |
| `container.init_resources()` | Lazy initialization — no equivalent needed | [§9](#9-testing-and-overrides) |
| `container.shutdown_resources()` / `provider.shutdown()` | `container.close_sync()` / `await container.close_async()` | [§9](#9-testing-and-overrides) |
| `provider.override(...)` / `with provider.override(...):` | `container.override(provider, mock)` / `with container.override(provider, mock):` — see [§9](#9-testing-and-overrides) | [§9](#9-testing-and-overrides) |
| `provider.reset_override()` / `provider.reset_last_overriding()` | `container.reset_override(provider)` | [§9](#9-testing-and-overrides) |

## 4. Migrate the dependency graph

1. Replace `DeclarativeContainer` with `Group`.
2. Add an explicit `scope=` to each provider (defaults to `Scope.APP`).
3. Create the runtime container with `Container(groups=[MyGroup], validate=True)`. In `modern-di`, `Group` is a schema only — you cannot resolve from it directly, unlike a `DeclarativeContainer` instance.

**`Singleton` / `ThreadSafeSingleton`** → `providers.Factory(SomeClass, cache=True)` — no separate thread-safe class, since `modern-di`'s cache is lock-guarded by default. See [Cached factories](../providers/factories.md#cached-factories).

**`Resource`** → cached `Factory`, with or without a `finalizer` depending on the initializer form. Their docs call the plain-function initializer "the most common way to specify resource initialization" — and a plain-function `Resource` has no shutdown step, so it maps to exactly what `Singleton` maps to:

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

**`ContextLocalResource`** → `REQUEST`-scoped cached `Factory` with a `finalizer`. `dependency-injector`'s `ContextLocalResource` uses `contextvars` to give each execution context (in practice: each async request) its own instance of a `Resource`, cleaned up when the context ends. `modern-di` expresses the same lifetime explicitly: declare the provider at `Scope.REQUEST` and resolve it from a per-request child container — the framework integrations build that child container for you ([§8](#8-framework-integration-and-routes)), and closing it runs the finalizer:

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

**`Callable`** → a plain `Factory` whose creator is the callable — `modern-di` has no separate "wraps a function vs. wraps a class" distinction; `Factory.creator` accepts any `Callable[..., T]`. Note the call-time argument this example passes (`container.password_hasher("super secret")`) has no `modern-di` equivalent — see the note below:

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

> **Providers are not partially-applied callables in `modern-di`.** In `dependency-injector`, every provider instance is itself callable, and calling it with extra positional/keyword arguments merges them with the declared ones for that one call (`container.some_factory(extra_arg)`). `modern-di`'s `Factory` has no equivalent: `resolve()`/`resolve_provider()` take no arguments, and every constructor argument must be resolvable (by type, by `kwargs`, or by default) at declaration time. If a value genuinely varies per call site, resolve a plain function or make it a `ContextProvider`/`Scope.REQUEST` dependency instead of trying to pass it at the call site.

**`Object`** → `Factory` whose creator returns the value. Define a small typed function (lambdas have no return annotation, which prevents resolution by type):

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

modules = providers.Factory(build_modules)
```

**`Dependency`** → `ContextProvider`. Both are a typed placeholder filled in at runtime rather than constructed by a factory:

```python
# dependency-injector
database = providers.Dependency(instance_of=DbAdapter)
# container = Container(database=providers.Singleton(SqliteDbAdapter))

# modern-di
database = providers.ContextProvider(DbAdapter, scope=Scope.APP)
# container = Container(groups=[AppGroup], context={DbAdapter: SqliteDbAdapter()})
```

**`AbstractFactory`** → `Alias`. `dependency-injector`'s `AbstractFactory` starts unbound and must be `.override()`-ed with a concrete `Factory` before first use; `modern-di` instead registers the concrete provider directly and re-exports it under the abstract type at declaration time — no override step, and `validate()` catches a missing binding before the first resolve:

```python
# dependency-injector
cache_client_factory = providers.AbstractFactory(AbstractCacheClient)
# container.cache_client_factory.override(providers.Factory(RedisCacheClient, host="localhost"))

# modern-di
redis_cache_client = providers.Factory(RedisCacheClient, cache=True)
cache_client = providers.Alias(RedisCacheClient, bound_type=AbstractCacheClient)
```

## 5. Configuration

`dependency-injector`'s `Configuration` provider is a subsystem: `providers.Configuration()` plus `.from_yaml()` / `.from_json()` / `.from_ini()` / `.from_env()` / `.from_pydantic()` / `.from_dict()` / `.from_value()` loaders, environment-variable interpolation (`${VAR:default}`), and a "use first, define later" declaration order. `modern-di` deliberately has no equivalent subsystem — this is a design decision, not a gap: load your settings with whatever library you already use (`pydantic-settings`, `environ-config`, plain `os.environ`, ...) into a regular object, then register that object as an ordinary provider:

```python
class Settings:
    def __init__(self) -> None:
        self.database_url = os.environ["DATABASE_URL"]

class AppGroup(Group):
    settings = providers.Factory(Settings, cache=True)
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

More framework examples in [§8](#8-framework-integration-and-routes).

This also removes `dependency-injector`'s most-filed failure mode: an unwired function's marker is left as a raw `Provide` object, which surfaces as a confusing `AttributeError: 'Provide' object has no attribute ...` deep in your own code ([issue #658](https://github.com/ets-labs/python-dependency-injector/issues/658), [issue #521](https://github.com/ets-labs/python-dependency-injector/issues/521)) rather than a DI-specific error at the point of the mistake. `modern-di` fails at declaration time (`UnsupportedCreatorParameterError`) or resolve time (`ProviderNotRegisteredError`, with "did you mean" suggestions) — see [§10](#10-diagnostics-comparison).

## 7. Scopes

`dependency-injector` has no ordered scope hierarchy. Each provider independently chooses a lifetime class (`Factory` = new object every call, `Singleton`/`ThreadSafeSingleton` = one object per container, `Resource` = one object with init/shutdown hooks), and request-scoped state is either threaded through the `Closing` wiring marker on a `Resource` or built with a second, request-scoped container instantiated per request. `modern-di` has one mechanism for both "create once" and "scoped to a boundary": `Scope.APP → SESSION → REQUEST → ACTION → STEP`, plus child containers.

```python
class AppGroup(Group):
    # one instance for the whole app's lifetime
    db_pool = providers.Factory(create_pool, scope=Scope.APP, cache=True)

    # one instance per request; built by build_child_container(scope=Scope.REQUEST)
    current_user = providers.Factory(UserFromRequest, scope=Scope.REQUEST)

app_container = Container(scope=Scope.APP, groups=[AppGroup], validate=True)
request_container = app_container.build_child_container(scope=Scope.REQUEST, context={...})
```

See [the scope dependency rule](../providers/scopes.md#the-scope-dependency-rule) for the equal-or-broader constraint and how `validate()` catches a violation before the first resolve. Framework integrations ([§8](#8-framework-integration-and-routes)) build and tear down the per-request child container automatically, the same role `Resource` + `Closing` (or a hand-rolled second container) plays in `dependency-injector`.

## 8. Framework integration and routes

Replace `container.wire(modules=[...])` (plus any per-framework glue such as `container` attributes on the app object) with the integration package's setup call ([FastAPI](../integrations/fastapi.md), [Litestar](../integrations/litestar.md), [FastStream](../integrations/faststream.md), [Typer](../integrations/typer.md)) — it creates per-request child containers, tears them down automatically, and calls `container.close_async()` at shutdown. There is no module list to maintain and no import-time patching. On routes, `FromDI(T)` replaces the `@inject` + `Provide[Container.x]` pair: resolution is by type, so no marker points at a specific container attribute and no `@inject` decorator is needed — see the integration pages for the full route examples.

## 9. Testing and overrides

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

`dependency-injector` also has a context-manager override form (`with container.api_client_factory.override(mock):`) that auto-resets on exit. `modern-di` has the same shape — `with container.override(provider, mock) as m:` applies the override for the block and restores the prior state on exit, including on exception:

```python
# modern-di
with container.override(AppGroup.api_client_factory, unittest.mock.Mock(ApiClient)) as mock_factory:
    ...
```

See [Testing with overrides](../recipes/testing-overrides.md) for tree-wide sharing, nesting, and reset mechanics.

### Lifecycle

- **No `init_resources()` equivalent** — providers initialize lazily on first resolve; see [Lazy initialization](../providers/lifecycle.md#lazy-initialization) for eager-warmup at startup.
- **`shutdown_resources()` / `provider.shutdown()` → `container.close_sync()` / `await container.close_async()`** (also usable as (async) context managers, finalizers running in reverse order on exit).

### Pytest

`modern-di-pytest` provides fixture-based wiring, replacing hand-written `container.override(...)` calls per test — see [the pytest integration](../integrations/pytest.md).

## 10. Diagnostics comparison

| Failure mode | `dependency-injector` | `modern-di` |
|---|---|---|
| Circular dependency | No cycle detection; a circular provider graph raises a bare `RecursionError` from Cython-level `deepcopy`, with no cycle path ([issue #811](https://github.com/ets-labs/python-dependency-injector/issues/811)) | `validate()` reports every cycle up front as `CircularDependencyError` with an arrow-chain `cycle_path`; even without `validate()`, a runtime cycle hit is caught and re-raised as `CircularDependencyError` (not a bare `RecursionError`) |
| Unwired injection point | Silent: an un-wired function keeps the raw `Provide` marker as its default, surfacing as `AttributeError: 'Provide' object has no attribute ...` far from the actual mistake ([#658](https://github.com/ets-labs/python-dependency-injector/issues/658), [#521](https://github.com/ets-labs/python-dependency-injector/issues/521)) | No marker subsystem to leave unwired: a missing dependency fails at declaration time (`UnsupportedCreatorParameterError`) or resolve time (`ProviderNotRegisteredError`, `ArgumentResolutionError`) |
| Whole-graph validation | None — errors surface one at a time, on first resolve, wherever the graph happens to break | `Container(..., validate=True)` walks the entire graph and raises one `ValidationFailedError` aggregating *every* wiring bug (cycles, inverted scopes, missing dependencies) at once |
| Resolve by type | [No type-based resolution API](https://python-dependency-injector.ets-labs.org/wiring.html) — every call site needs an explicit `Provide[Container.x]` marker | `container.resolve(SomeType)` resolves directly from a type annotation; unregistered types get closest-match ("did you mean") suggestions |

Run with `validate=True` during migration — the cycle row above is considerably noisier without it, since the error surfaces deep inside an already near-exhausted call stack instead of a clean, aggregated report.

## 11. No direct equivalent

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
