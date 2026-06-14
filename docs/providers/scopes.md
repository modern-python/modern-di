# Scopes

A scope is the lifetime band that a provider lives in. `modern-di` has five built-in scopes, ordered from longest-lived to shortest:

```
APP → SESSION → REQUEST → ACTION → STEP
```

`Scope` is an `IntEnum` — `APP=1`, `SESSION=2`, `REQUEST=3`, `ACTION=4`, `STEP=5`. The higher the int, the shorter the lifetime.

## What each scope is for

| Scope | Typical use |
|---|---|
| `APP` | One-per-process resources: settings, the database engine, a Redis client, a Kafka producer. The default if you omit `scope=`. |
| `SESSION` | One-per-websocket-connection resources. Framework integrations enter SESSION automatically when a websocket opens. |
| `REQUEST` | One-per-HTTP-request resources: the database session, the per-request user repository, the current `Request` object. Framework integrations create the REQUEST child container for each incoming request. |
| `ACTION` | A sub-step inside a request — e.g. one item in a batch handler that should get its own cached values. Enter manually with `build_child_container`. |
| `STEP` | A sub-step inside an ACTION. Same idea, one level deeper. |

`APP` and `REQUEST` cover the vast majority of real apps. Reach for `SESSION` only for websockets; `ACTION`/`STEP` are for cases where you want isolated caching inside a request.

## The container tree

The root `Container` is at `APP` scope. Child containers are built from a parent via `build_child_container(scope=...)`, where the child's scope must be *higher* (shorter-lived) than the parent's.

```python
from modern_di import Container, Scope


app_container = Container(groups=[Dependencies])     # APP scope

with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
    ...
```

`Dependencies` here is a `Group` subclass holding the provider definitions — see the [Quick Start](../index.md) or [Resolving dependencies](../introduction/resolving.md) for how it's declared.

Children share their parent's `providers_registry` (provider definitions) and `overrides_registry` (test overrides) but have their own `cache_registry` (resolved instances) and `context_registry` (runtime context values). That's why a REQUEST-scoped factory produces one instance per request — the cache lives on the request container, not the app container.

## The scope dependency rule

**A provider can only depend on providers at the same scope or a broader (lower int) scope.** A REQUEST-scoped session can consume the APP-scoped engine. The engine cannot consume the session.

Why: lifetime safety. If an APP-scoped singleton held a reference to a REQUEST-scoped session, the session would outlive its request and produce stale state. `Container(groups=[...], validate=True)` enforces this at startup — turn it on.

### How to choose a scope

A provider's scope should be the **maximum** scope value among all its dependencies (i.e. the shortest-lived one). Examples:

- A provider depends on an APP-scoped engine and a REQUEST-scoped session → REQUEST.
- A provider has no dependencies → APP (the default).
- A provider depends only on APP-scoped providers → APP.

If you pick a broader scope than the rule allows, `validate=True` catches it at startup.

## Building child containers

Two patterns:

**Manual.** Use the child container as a context manager so finalizers run on exit:

```python
with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
    service = request_container.resolve(UserService)
# finalizers ran here

async with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
    service = request_container.resolve(UserService)
# async finalizers ran here
```

Use `async with` only when the scope holds providers with async finalizers; otherwise plain `with` is enough. Resolution itself is always synchronous.

**Framework-managed.** Integration packages (`modern-di-fastapi`, `modern-di-litestar`, `modern-di-faststream`) build the REQUEST child container for each request and tear it down at the end. You only declare `scope=Scope.REQUEST` on the providers that need it.

## Resolving across scopes

Resolution looks up each parameter's type in the providers registry, finds the container at that provider's declared scope, and resolves from there. If you resolve an APP-scoped provider from a REQUEST container, you transparently walk up to the APP container — the cached APP instance is returned.

```python
# REQUEST container can resolve APP-scoped providers
engine: AsyncEngine = request_container.resolve(AsyncEngine)  # walks up to APP
session: AsyncSession = request_container.resolve(AsyncSession)  # local to REQUEST
```

Trying to resolve a REQUEST-scoped provider from an APP container raises [`ScopeNotInitializedError`](errors-and-exceptions.md) — the request container hasn't been built yet, so there's nothing to resolve into.

## Custom scopes

For non-standard lifecycles (per-tenant containers, background-job runs, anything that doesn't fit the built-in five), pass any `IntEnum` value where `Scope` is accepted:

```python
from enum import IntEnum
from modern_di import Container, Group, providers


class MyScope(IntEnum):
    TENANT = 6
    BACKGROUND_JOB = 7


class TenantContext:
    pass


class MyGroup(Group):
    tenant_provider = providers.Factory(scope=MyScope.TENANT, creator=TenantContext)


container = Container(groups=[MyGroup])
with container.build_child_container(scope=MyScope.TENANT) as tenant_container:
    tenant = tenant_container.resolve(TenantContext)
```

The child scope's integer value must be strictly greater than its parent's. When `scope=` is omitted from `build_child_container`, the auto-derived next scope only advances within the parent's own enum class — to cross enum boundaries (e.g. jump from a built-in `Scope` to `MyScope.TENANT`), pass `scope=` explicitly.

## See also

- [Lifecycle](lifecycle.md) — finalizers and `close_async()` work per-scope.
- [Container Provider](container.md) — injecting the active container into a creator.
- [Async resources via lifespan](../recipes/async-lifespan.md) — pattern for APP-scoped async setup.
