# Scopes

A scope is how long a provider's instances live. `modern-di` has five built-in scopes, from
longest-lived to shortest:

```
APP → SESSION → REQUEST → ACTION → STEP
```

`Scope` is an `IntEnum`: `APP=1`, `SESSION=2`, `REQUEST=3`, `ACTION=4`, `STEP=5`. A higher number
is a shorter lifetime, and this page calls that scope deeper.

## What each scope is for

| Scope | Typical use |
|---|---|
| `APP` | One per process: settings, the database engine, a Redis client, a Kafka producer. The default when you omit `scope=`. |
| `SESSION` | One per websocket connection. The FastAPI, Starlette, Litestar and aiohttp integrations enter it when a websocket opens. |
| `REQUEST` | One per HTTP request or broker message: the database session, the current `Request`. Framework integrations build a REQUEST container for each one. |
| `ACTION` | A unit of work inside a request that needs its own cached values, such as one item in a batch. You enter it yourself. |
| `STEP` | One level below `ACTION`, for the same purpose. |

Most apps need only `APP` and `REQUEST`. HTTP requests skip `SESSION`: the integration builds the
REQUEST container directly under APP, so a SESSION-scoped provider is available only inside a
websocket.

## Scope and caching

A provider's scope picks the container that owns it. With `cache=True`, that container creates the
instance once, returns it on every resolve, and runs its finalizer when it closes. A cached
REQUEST-scoped provider gives one instance per request.

Without `cache`, every resolve creates a new object, whatever the scope. The scope still decides
where the provider can be resolved and what it may depend on: an uncached REQUEST factory can take
the request's database session as an argument, and an APP one cannot.

<!-- invisible-code-block: python
from modern_di import Group, Scope, providers


class AsyncEngine: ...


class AsyncSession:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


class Dependencies(Group):
    engine = providers.Factory(AsyncEngine, cache=True)
    session = providers.Factory(AsyncSession, scope=Scope.REQUEST, cache=True)
    user_service = providers.Factory(UserService, scope=Scope.REQUEST)
-->

```python
from modern_di import Container, Scope


app_container = Container(groups=[Dependencies])

with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
    # session is cached, user_service is not
    assert request_container.resolve(AsyncSession) is request_container.resolve(AsyncSession)
    assert request_container.resolve(UserService) is not request_container.resolve(UserService)
```

`Dependencies` is a `Group` subclass holding the provider definitions; the
[Quickstart](../index.md) shows how one is declared.

## Building child containers

The root `Container` is at `APP` scope. `build_child_container(scope=...)` builds a child at a
deeper scope. The child shares its parent's providers and test overrides, and keeps its own cache
and [context](context.md) values. Use it as a context manager so its finalizers run on exit:

```python
with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
    service = request_container.resolve(UserService)
# REQUEST finalizers have run here
```

If a cached instance in the container has an async finalizer, use `async with`. Leaving a plain
`with` raises [`AsyncFinalizerInSyncCloseError`](../troubleshooting/async-finalizer-in-sync-close-error.md)
inside a `FinalizerError`. Resolving stays synchronous either way:

```python
async with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
    service = request_container.resolve(UserService)
```

Without `scope=`, the child takes the next scope down: APP builds SESSION, SESSION builds REQUEST.
There is nothing below STEP, so a child of a STEP container raises
[`MaxScopeReachedError`](../troubleshooting/max-scope-reached-error.md).

A child can skip scopes, the way HTTP integrations go from APP straight to REQUEST. A provider at a
skipped scope then raises [`ScopeSkippedError`](../troubleshooting/scope-skipped-error.md) in that
chain:

<!-- raises: ScopeSkippedError -->
```python
class WebsocketState: ...


class WebsocketDependencies(Group):
    state = providers.Factory(WebsocketState, scope=Scope.SESSION, cache=True)


container = Container(groups=[WebsocketDependencies])
with container.build_child_container(scope=Scope.REQUEST) as request_container:
    request_container.resolve(WebsocketState)
```

A [framework integration](../integrations/fastapi.md) builds and closes the child container for
each request or message, so you only declare `scope=Scope.REQUEST` on the providers that need it.
You build children yourself for `ACTION` and `STEP`, or for work that runs outside a framework.

## Resolving across scopes

A provider resolves in the container at its own scope. From a REQUEST container, an APP-scoped
provider resolves in the APP container and returns the instance cached there:

```python
with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
    engine = request_container.resolve(AsyncEngine)  # cached in the APP container
    session = request_container.resolve(AsyncSession)  # cached in this REQUEST container
    assert engine is app_container.resolve(AsyncEngine)
```

The other direction fails. Resolving a REQUEST-scoped provider from the APP container raises
[`ScopeNotInitializedError`](../troubleshooting/scope-not-initialized-error.md), because no REQUEST
container exists to hold it.

## The scope dependency rule

A provider may depend only on providers at its own scope or a shallower one. The REQUEST-scoped
session can take the APP-scoped engine, and the engine cannot take the session.

A provider that breaks the rule is a **captive dependency**: a long-lived object that would keep a
short-lived one past the end of its scope, such as an APP singleton holding the first request's
session. `modern-di` never builds one. `container.validate()` reports it at startup as
[`InvalidScopeDependencyError`](../troubleshooting/scope-chain.md), and resolving it without
validation raises `ScopeNotInitializedError`. Call `validate()` at startup to find it before the
first request. [Good and bad practices](../recipes/good-and-bad-practices.md#1-captive-dependency-a-wide-scoped-provider-holding-a-narrow-scoped-one)
walks through the mistake and the fix.

### How to choose a scope

The deepest scope among a provider's dependencies is the shallowest scope it can have:

- A provider that depends on the APP engine and the REQUEST session needs at least `REQUEST`.
- A provider that depends only on APP providers, or on nothing, can be `APP`.

Go deeper when you want one instance per request or per action, closed when it ends. A unit of work
with no dependencies can still be a cached REQUEST provider. If you choose a scope that is too
shallow, `validate()` reports it.

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
    tenant_provider = providers.Factory(TenantContext, scope=MyScope.TENANT)


container = Container(groups=[MyGroup])
with container.build_child_container(scope=MyScope.TENANT) as tenant_container:
    tenant = tenant_container.resolve(TenantContext)
```

The child scope's integer value must be strictly greater than its parent's. When `scope=` is omitted from `build_child_container`, the auto-derived next scope only advances within the parent's own enum class. To cross enum boundaries (e.g. jump from a built-in `Scope` to `MyScope.TENANT`), pass `scope=` explicitly.

A provider resolves only in a container built at the same enum member. Members of different enums that share an integer value are different scopes: with `class Tenancy(IntEnum): TENANT = 2`, a provider at `Tenancy.TENANT` does not resolve in a `Scope.SESSION` container, and raises [`ScopeSkippedError`](../troubleshooting/scope-skipped-error.md) there. `validate()` reports a provider that depends on such a scope as [`ScopeEnumMismatchError`](../troubleshooting/scope-enum-mismatch-error.md). Ordering still compares integer values, which is why `MyScope.TENANT = 6` can be a child of `Scope.APP`.

## Group-level default scope

When declaring providers in a `Group` subclass, you can assign a default scope to all members using the class kwarg:

```python
from modern_di import Container, Group, Scope, providers


class UserRepository:
    pass


class AuditLog:
    pass


class RequestGroup(Group, scope=Scope.REQUEST):
    repo = providers.Factory(UserRepository)              # inherits group default: REQUEST
    audit = providers.Factory(AuditLog, scope=Scope.APP)  # explicit scope wins


app_container = Container(groups=[RequestGroup])
with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
    repo = request_container.resolve(UserRepository)
```

Scope resolution follows a priority order:

1. An explicit `scope=` on the provider always wins.
2. Then the group's `scope=` kwarg, inherited via MRO by subclasses. A subclass may override it with its own `scope=` kwarg, which applies to the providers declared in its own body; inherited providers keep the scope their declaring class gave them.
3. Otherwise `Scope.APP`, the final default.

`Alias` providers do not participate in group-level scope defaults; an alias's scope always derives from its source.

A scope-defaulted provider instance that is shared between two `Group` subclasses with different defaults raises [`GroupScopeConflictError`](../troubleshooting/group-scope-conflict-error.md) at class-creation time. Sharing the same provider instance with the same default scope across multiple groups is allowed.

A group declared without a `scope=` kwarg stamps nothing, so a provider listed only in such a group keeps the `Scope.APP` default and can still be stamped by a later group, but only until it is registered with a container. After that, a group that would *change* its scope raises [`ProviderScopeFrozenError`](../troubleshooting/provider-scope-frozen-error.md), because resolvers compiled before the change already captured the old scope. Declare every group that lists a provider before building the container, or set `scope=` on the provider explicitly.

## See also

- [Lifecycle](lifecycle.md): finalizers and `close_async()` work per-scope.
- [Container](container.md): injecting the active container into a creator.
- [Context providers](context.md): passing values into a child container with `context=`.
- [Async resources via lifespan](../recipes/async-lifespan.md): pattern for APP-scoped async setup.
