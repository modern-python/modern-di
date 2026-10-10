# Organize a large container with multiple Groups

Your application has 30+ providers, and one `Group` holding all of them is unreadable.

## Solution

Split providers into several `Group` subclasses by domain (database, cache, repositories, use cases) and pass them all to `Container(groups=[...])`. Dependencies between groups wire by type, so no group refers to another.

```python
import dataclasses

import redis.asyncio as aioredis
import sqlalchemy.ext.asyncio as sa_async
from modern_di import Container, Group, Scope, providers


def create_engine() -> sa_async.AsyncEngine:
    return sa_async.create_async_engine("postgresql+asyncpg://localhost/app")


def create_session(engine: sa_async.AsyncEngine) -> sa_async.AsyncSession:
    return sa_async.AsyncSession(engine, expire_on_commit=False)


def create_redis() -> aioredis.Redis:
    return aioredis.Redis.from_url("redis://localhost")


@dataclasses.dataclass
class UserRepository:
    session: sa_async.AsyncSession


@dataclasses.dataclass
class OrderRepository:
    session: sa_async.AsyncSession


@dataclasses.dataclass
class PlaceOrder:
    users: UserRepository
    orders: OrderRepository
    cache: aioredis.Redis


@dataclasses.dataclass
class CancelOrder:
    orders: OrderRepository


class Database(Group):
    engine = providers.Factory(
        create_engine,
        scope=Scope.APP,
        cache=providers.CacheSettings(finalizer=sa_async.AsyncEngine.dispose),
    )
    session = providers.Factory(
        create_session,
        scope=Scope.REQUEST,
        cache=providers.CacheSettings(finalizer=sa_async.AsyncSession.close),
    )


class Cache(Group):
    redis_client = providers.Factory(
        create_redis,
        scope=Scope.APP,
        cache=providers.CacheSettings(finalizer=aioredis.Redis.aclose),
    )


class Repositories(Group, scope=Scope.REQUEST):
    users = providers.Factory(UserRepository)
    orders = providers.Factory(OrderRepository)


class UseCases(Group, scope=Scope.REQUEST):
    place_order = providers.Factory(PlaceOrder)
    cancel_order = providers.Factory(CancelOrder)


ALL_GROUPS = [Database, Cache, Repositories, UseCases]

container = Container(groups=ALL_GROUPS)
container.validate()
```

`Repositories` and `UseCases` set `scope=Scope.REQUEST` once on the class instead of on every provider; see [Group-level default scope](../providers/scopes.md#group-level-default-scope).

`PlaceOrder` depends on providers from three other groups: the repositories, the Redis client from `Cache`, and through the repositories the session from `Database`. Inside one request both repositories get the same cached session:

```python
import sqlalchemy.ext.asyncio as sa_async

async with container.build_child_container(scope=Scope.REQUEST) as request_container:
    place_order = request_container.resolve(PlaceOrder)
    session = request_container.resolve(sa_async.AsyncSession)
    assert place_order.users.session is session
    assert place_order.orders.session is session
```

<!-- invisible-code-block: python
import sqlalchemy

await container.close_async()
-->

## Pitfalls

- Two providers for the same type make `Container(groups=[...])` raise `DuplicateProviderTypeError`, whichever groups they are in. Give one of them `bound_type=None` and pass it to its consumers through [`kwargs`](../providers/factories.md#kwargs); see [DuplicateProviderTypeError](../troubleshooting/duplicate-type-error.md).
- A provider object belongs to one group. Assigning it to a second group (`engine = Database.engine`) registers it twice and raises the same `DuplicateProviderTypeError`. To use another group's provider, depend on its type, or reference it in `kwargs={"engine": Database.engine}`.
- Passing one group twice, or a group together with its subclass, also registers the same providers twice and raises `DuplicateProviderTypeError`, with a `bound_type=None` hint that does not apply. Pass each group once; for a subclass, pass only the subclass. See [issue #669](https://github.com/modern-python/modern-di/issues/669).
- `Container` ignores attribute names, so two groups can both have a `session` attribute. Litestar's `autowired_groups` and `modern-di-pytest`'s `expose()` do use them: the first warns and keeps the provider from the last group, and the second raises `ValueError`.
- The order of `groups=[...]` does not matter. Nothing checks the combined graph for you, so call `container.validate()` at startup.

## Auto-wiring with Litestar

On Litestar, pass `autowired_groups=ALL_GROUPS` to `ModernDIPlugin` and every provider in those groups becomes a Litestar dependency named after its attribute. A handler receives one by naming a parameter after it, `place_order: NamedDependency[PlaceOrder]`, with no per-route `FromDI`:

```python
from litestar import Litestar
from modern_di_litestar import ModernDIPlugin

app = Litestar(
    plugins=[ModernDIPlugin(container, autowired_groups=ALL_GROUPS)],
)
```

See [Auto-wiring with `autowired_groups`](../integrations/litestar.md#auto-wiring-with-autowired_groups) for a handler and the name-collision rules.

## See also

- [Factories](../providers/factories.md), [Scopes](../providers/scopes.md).
- [Litestar integration](../integrations/litestar.md): `autowired_groups`.
- [Async SQLAlchemy recipe](sqlalchemy.md): the building blocks for the `Database` group above.
