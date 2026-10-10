# Testing with overrides

Tests often need to swap a real dependency (database, HTTP client, clock) for a fake one without touching production wiring. `container.override(provider, replacement)` makes every resolve of that provider return the replacement until the override is reset.

## Override with a context manager

`override()` returns an `OverrideHandle`. Used in a `with` block, it resets the override on exit, which makes it the primary spelling for tests:

<!-- invisible-code-block: python
from modern_di import Container, Group, providers


class ApiClient: ...


class MyGroup(Group):
    api_client = providers.Factory(ApiClient)


container = Container(groups=[MyGroup])
mock_client = ApiClient()
-->

```python
with container.override(MyGroup.api_client, mock_client) as client:
    assert container.resolve(ApiClient) is client
```

The override takes effect at the `override()` call, and `with` hands back the replacement. On exit, even after an exception or a `reset_override()` inside the block, the handle restores what was active at the call: an earlier override of the same provider, or none. Nested overrides of one provider unwind in reverse order, as nested `with` blocks do; exiting handles out of order can restore stale state.

Overrides are keyed by provider object and stored once for the whole container tree. An override set on any container, the root or a REQUEST child, applies to every container that shares its root.

## Imperative override and reset

Without `with`, `override()` applies until you reset it:

```python
container.override(MyGroup.api_client, mock_client)
assert container.resolve(ApiClient) is mock_client
container.reset_override(MyGroup.api_client)
```

`container.reset_override()` with no argument clears every override. Closing a container does not clear them.

## Container fixtures without the plugin

You can test without [`modern-di-pytest`](../integrations/pytest.md): build the container in a session-scoped fixture, build a REQUEST child per test, and set overrides in function-scoped fixtures:

<!-- invisible-code-block: python
import dataclasses
import sys
import types

from modern_di import Group, Scope, providers


class UserRepository:
    def name(self, user_id: int) -> str:
        return f"user-{user_id}"


@dataclasses.dataclass
class Greeter:
    users: UserRepository

    def greet(self, user_id: int) -> str:
        return f"Hello, {self.users.name(user_id)}"


class Dependencies(Group):
    user_repository = providers.Factory(UserRepository, scope=Scope.APP, cache=True)
    greeter = providers.Factory(Greeter, scope=Scope.REQUEST)


app_module = types.ModuleType("app")
ioc_module = types.ModuleType("app.ioc")
services_module = types.ModuleType("app.services")
ioc_module.Dependencies = Dependencies
ioc_module.ALL_GROUPS = [Dependencies]
services_module.Greeter = Greeter
services_module.UserRepository = UserRepository
app_module.ioc = ioc_module
app_module.services = services_module
sys.modules.update({"app": app_module, "app.ioc": ioc_module, "app.services": services_module})
del UserRepository, Greeter, Dependencies
-->

```python
import typing

import modern_di
import pytest

from app import ioc
from app.services import Greeter, UserRepository


class FakeUserRepository(UserRepository):
    def name(self, user_id: int) -> str:
        return "fake"


@pytest.fixture(scope="session")
def di_container() -> typing.Iterator[modern_di.Container]:
    with modern_di.Container(groups=ioc.ALL_GROUPS) as container:
        container.validate()
        yield container


@pytest.fixture
def request_container(di_container: modern_di.Container) -> typing.Iterator[modern_di.Container]:
    with di_container.build_child_container(scope=modern_di.Scope.REQUEST) as container:
        yield container


@pytest.fixture
def fake_users(di_container: modern_di.Container) -> typing.Iterator[FakeUserRepository]:
    with di_container.override(ioc.Dependencies.user_repository, FakeUserRepository()) as fake:
        yield fake


def test_greeting(request_container: modern_di.Container, fake_users: FakeUserRepository) -> None:
    assert request_container.resolve(Greeter).greet(1) == "Hello, fake"
```

<!-- invisible-code-block: python
with modern_di.Container(groups=ioc.ALL_GROUPS) as root:
    with root.override(ioc.Dependencies.user_repository, FakeUserRepository()) as fake:
        with root.build_child_container(scope=modern_di.Scope.REQUEST) as child:
            test_greeting(child, fake)
    with root.build_child_container(scope=modern_di.Scope.REQUEST) as child:
        assert child.resolve(Greeter).greet(1) == "Hello, user-1"

for stand_in in ("app", "app.ioc", "app.services"):
    sys.modules.pop(stand_in)
-->

`Greeter` is REQUEST-scoped, so the test resolves it from `request_container`; resolving it from `di_container` raises `ScopeNotInitializedError`. The override sits on the session-scoped container, so `fake_users` has to undo it after each test, and the `with` block does that even when the test fails. To get dependencies as fixtures instead of resolving them in the test, see [Pytest integration](../integrations/pytest.md): [Pointing a fixture at a child container](../integrations/pytest.md#pointing-a-fixture-at-a-child-container) and [Overrides](../integrations/pytest.md#overrides).

## Transactional database tests

For tests against a real database, run each test inside a transaction and roll it back at the end. Override the engine provider from the [Async SQLAlchemy recipe](sqlalchemy.md) with a connection that holds the open transaction, so every session built during the test uses that connection:

<!-- invisible-code-block: python
import sys
import types

import sqlalchemy.ext.asyncio as sa_async
from modern_di import Group, Scope, providers


def create_engine() -> sa_async.AsyncEngine:
    return sa_async.create_async_engine("postgresql+asyncpg://localhost/app")


class Dependencies(Group):
    engine = providers.Factory(create_engine, scope=Scope.APP, cache=True)


app_module = types.ModuleType("app")
ioc_module = types.ModuleType("app.ioc")
ioc_module.Dependencies = Dependencies
app_module.ioc = ioc_module
sys.modules.update({"app": app_module, "app.ioc": ioc_module})
del Dependencies
-->

```python
import typing

import modern_di
import pytest
import sqlalchemy.ext.asyncio as sa_async

from app import ioc


@pytest.fixture
async def db_connection(
    di_container: modern_di.Container,
) -> typing.AsyncIterator[sa_async.AsyncConnection]:
    engine = sa_async.create_async_engine("postgresql+asyncpg://user:pass@localhost/test")
    async with engine.connect() as connection:
        transaction = await connection.begin()
        with di_container.override(ioc.Dependencies.engine, connection):
            yield connection
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def session(
    db_connection: sa_async.AsyncConnection,
    di_container: modern_di.Container,
) -> typing.AsyncIterator[sa_async.AsyncSession]:
    async with di_container.build_child_container(scope=modern_di.Scope.REQUEST) as request_container:
        yield request_container.resolve(sa_async.AsyncSession)
```

<!-- invisible-code-block: python
import sqlalchemy

for stand_in in ("app", "app.ioc"):
    sys.modules.pop(stand_in)
-->

The session is REQUEST-scoped, so the `session` fixture resolves it from a REQUEST child, which also closes it after the test. Async fixtures need an async test plugin; with pytest-asyncio, set `asyncio_mode = "auto"` so plain `@pytest.fixture` works on them.

Build the session with `join_transaction_mode="create_savepoint"`:

```python
import sqlalchemy.ext.asyncio as sa_async


def create_session(engine: sa_async.AsyncEngine) -> sa_async.AsyncSession:
    return sa_async.AsyncSession(engine, expire_on_commit=False, join_transaction_mode="create_savepoint")
```

Under the default mode, a `session.rollback()` in the code under test rolls back the test's transaction too, and the fixture's own rollback then emits `SAWarning: transaction already deassociated from connection`. With `create_savepoint`, the session commits and rolls back a savepoint inside the test's transaction, and the fixture's rollback discards everything. In production the session is bound to an engine, not to a connection already in a transaction, and the option has no effect.

## Pitfalls

- Overrides are global to the container tree. Override on any container and every container sharing its root sees the replacement. That is what tests want; keep it in mind if you ever override outside tests.
- `override` is keyed by provider object. Pass `Dependencies.user_repository`, not the string `"user_repository"`, which raises `AttributeError`.
- Always reset. A leaked override reaches every later test that shares the container, and nothing reports it. With a session-scoped container, set overrides in a function-scoped fixture with `with container.override(...)`, so they are reset after each test even when it fails.
- Watch cached dependents. A cached instance (`cache=True`) keeps the dependencies it was built with, so overriding one of its dependencies does not reach an instance already in the cache, and an instance first built under an override keeps the fake after the override ends. Override the cached provider itself, or build the tests that need the fake a fresh container. [Pytest integration: Overrides](../integrations/pytest.md#overrides) has the same caveat for session-scoped fixtures.
- Override the right level. If you override the engine but tests resolve the session, the session's creator still runs, so the replacement has to be something that creator accepts. If a test relies on a specific session, override the session itself.

## See also

- [Pytest integration](../integrations/pytest.md).
- [Async SQLAlchemy recipe](sqlalchemy.md): the engine/session/repository chain being overridden here.
- Reference template: [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template) has the full transactional fixture setup.
