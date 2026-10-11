# Good and bad practices

modern-di's docs mostly show the happy path. This page collects the footguns instead: real
mistakes the framework lets you make, each paired with the mechanism that catches or prevents it.

## 1. Captive dependency: a wide-scoped provider holding a narrow-scoped one

A *captive dependency* is a wide-scoped provider holding a narrow-scoped one it cannot outlive. See
[the scope dependency rule](../providers/scopes.md#the-scope-dependency-rule) for why.

<!-- invisible-code-block: python
from modern_di import Container, Group, Scope, providers


class Session: ...


class UserCache:
    def __init__(self, session: Session) -> None:
        self.session = session
-->

```python
class Dependencies(Group):
    session = providers.Factory(Session, scope=Scope.REQUEST)

    # Broken: forgot scope=Scope.REQUEST, so it defaults to Scope.APP, which cannot hold `session`
    user_cache = providers.Factory(UserCache)

    # Works: matches the lifetime of what it consumes
    user_cache = providers.Factory(UserCache, scope=Scope.REQUEST)
```

`container.validate()` reports the broken version before anything resolves: it raises
`ValidationFailedError` carrying an `InvalidScopeDependencyError`; see
[InvalidScopeDependencyError](../troubleshooting/scope-chain.md). Without `validate()`, the first resolve of
`UserCache` raises `ScopeNotInitializedError`, whose message names both `UserCache` and `Session`, on
the first request that reaches it instead of at startup.

## 2. Shipping a never-validated graph

`validate()` is the only check of the whole graph: cycles, scope violations, and dependencies
nothing provides. Nothing calls it for you; see [Validation](../providers/lifecycle.md#validation).

```python
# Broken: never validated, so wiring bugs surface one at a time, in production, on whatever request trips them
container = Container(groups=[Dependencies])

# Works: validated explicitly, so every wiring bug is reported at once, at startup
container = Container(groups=[Dependencies])
container.validate()  # raises ValidationFailedError here if the graph is broken
```

`validate()` skips a provider declared with `bound_type=None` unless a provider registered by type
depends on it, so such a provider can still fail on its first resolve. An unvalidated cyclic graph
does not hang; see
[the runtime cycle guard](../troubleshooting/circular-dependency.md#the-runtime-cycle-guard-without-validate).

## 3. A cached factory resolved before `set_context`

A cached factory is built once, and a later `set_context` does not rebuild it. An uncached factory
reads the context again on every resolve.

<!-- invisible-code-block: python
class TenantConfig:
    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id


def create_tenant_config(tenant_id: str) -> TenantConfig:
    return TenantConfig(tenant_id)
-->

```python
class Dependencies(Group):
    tenant_id = providers.ContextProvider(str, scope=Scope.REQUEST)

    # Broken: cached, so it is built on first resolve and frozen from then on
    tenant_config = providers.Factory(create_tenant_config, scope=Scope.REQUEST, cache=True)

    # Works: uncached, so it re-reads the live context on every resolve
    tenant_config = providers.Factory(create_tenant_config, scope=Scope.REQUEST)
```

If a request container resolves `tenant_config` before the real tenant ID is set, the cached instance
keeps the earlier value for the rest of the request. Drop `cache=True` for anything that depends on
context set later, or set the context before the first resolve. `validate()` cannot catch this,
because the graph is correct and only the timing is wrong. See
[Context propagation](../providers/context.md#context-propagation).

## 4. Service location through an injected `Container`

A creator can take the resolving `Container` as a parameter; see
[Injecting the container itself](../providers/container.md#injecting-the-container-itself). Using it
to pull the creator's real dependencies out of the container turns DI into a service locator: the
dependency disappears from the signature and from `validate()`.

<!-- invisible-code-block: python
class Settings:
    api_key = "secret"
-->

```python
# Broken: the real dependency (Settings) is invisible to validate() and to the signature
def create_api_key(container: Container) -> str:
    return container.resolve(Settings).api_key

# Works: declared as an ordinary parameter, so validate() checks it
def create_api_key(settings: Settings) -> str:
    return settings.api_key
```

When nothing provides `Settings`, the broken version passes `validate()` and raises
`ProviderNotRegisteredError` on its first resolve, while `validate()` reports the declared parameter
up front. Keep `Container` parameters for code that is about the container, such as building a child
container.

## 5. Override leaks across tests

Overrides are shared by the whole container tree (see [Testing with overrides](testing-overrides.md)),
so one that is never reset reaches every later test that shares the container. Nothing reports the
leak.

<!-- invisible-code-block: python
import typing
from unittest.mock import Mock

import pytest
-->

```python
class Clock:
    def now(self) -> float:
        return 0.0


class Dependencies(Group):
    clock = providers.Factory(Clock)


container = Container(groups=[Dependencies])


# Broken: nothing resets the override, so every later test that resolves Clock gets the fake
def test_one() -> None:
    container.override(Dependencies.clock, Mock(spec=Clock))


# Works: the with block resets the override after each test, even when the test fails
@pytest.fixture
def fake_clock() -> typing.Iterator[Mock]:
    with container.override(Dependencies.clock, Mock(spec=Clock)) as fake:
        yield fake
```

<!-- invisible-code-block: python
test_one()
assert isinstance(container.resolve(Clock), Mock)
container.reset_override()
assert isinstance(container.resolve(Clock), Clock)
-->

`reset_override(provider)`, or `reset_override()` with no argument, clears an imperative override.
Closing the container does not. See [Testing with overrides](testing-overrides.md#pitfalls).

## 6. `skip_creator_parsing=True` with no `bound_type`

`skip_creator_parsing=True` turns off signature introspection, for creators modern-di cannot
introspect. It also skips the return annotation, so the provider has no bound type unless you pass
one: `Factory(...)` warns at declaration, and resolving the type raises `ProviderNotRegisteredError`.
See [`skip_creator_parsing`](../providers/factories.md#skip_creator_parsing).

<!-- invisible-code-block: python
class MyClass: ...


def opaque_creator() -> MyClass:
    return MyClass()
-->

<!-- raises: UserWarning -->

```python
# Broken: nothing else can resolve this provider by type, and a UserWarning fires at declaration time
providers.Factory(opaque_creator, scope=Scope.APP, skip_creator_parsing=True)

# Works: the type is declared explicitly
providers.Factory(
    opaque_creator,
    scope=Scope.APP,
    skip_creator_parsing=True,
    bound_type=MyClass,
)
```

The warning is easy to miss in test output. Treat it as a signal to add `bound_type=`.

## 7. Async finalizer on a container closed with `close_sync()`

`close_sync()` cannot await, and a sync `with container:` block closes with it. An async finalizer
there fails with `AsyncFinalizerInSyncCloseError` inside a `FinalizerError`, and the instance stays
cached until `close_async()` runs. The Celery integration closes the APP container with
`close_sync()`. See [Async finalizers and `close_sync()`](../providers/lifecycle.md#async-finalizers-and-close_sync).

```python
class HttpClient: ...


async def close_client(client: HttpClient) -> None: ...


class ClientDependencies(Group):
    client = providers.Factory(HttpClient, cache=providers.CacheSettings(finalizer=close_client))
```

<!-- raises: FinalizerError -->

```python
# Broken: `with` closes the container with close_sync(), which cannot await close_client
with Container(groups=[ClientDependencies]) as client_container:
    client_container.resolve(HttpClient)
```

```python
# Works: `async with` closes the container with close_async()
async with Container(groups=[ClientDependencies]) as client_container:
    client_container.resolve(HttpClient)
```

## See also

- [Errors and exceptions](../providers/errors-and-exceptions.md): the full catalog this page draws
  its mechanisms from.
- [Testing with overrides](testing-overrides.md): the full override lifecycle.
- [Lifecycle](../providers/lifecycle.md): caching, finalizers, and `validate()`.
