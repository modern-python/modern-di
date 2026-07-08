# Organize a large container with multiple Groups

**Problem.** Your service has 30+ providers and stuffing them all into one `Group` is unreadable.

## Solution

Split providers into multiple `Group` subclasses by domain — database, cache, messaging, use cases — and pass them all to `Container(groups=[...])`. Cross-group dependencies wire by type, with no explicit references between groups.

```python
import redis.asyncio as aioredis
import sqlalchemy.ext.asyncio as sa_async
from modern_di import Container, Group, Scope, providers


# --- factory functions (defined once, shared across groups) ---

def create_engine() -> sa_async.AsyncEngine:
    return sa_async.create_async_engine("postgresql+asyncpg://localhost/app")


async def close_engine(engine: sa_async.AsyncEngine) -> None:
    await engine.dispose()


def create_session(engine: sa_async.AsyncEngine) -> sa_async.AsyncSession:
    return sa_async.AsyncSession(engine, expire_on_commit=False)


async def close_session(session: sa_async.AsyncSession) -> None:
    await session.close()


def create_redis() -> aioredis.Redis:
    return aioredis.Redis.from_url("redis://localhost")


async def close_redis(client: aioredis.Redis) -> None:
    await client.aclose()


# --- groups ---

class Database(Group):
    engine = providers.Factory(
        create_engine,
        scope=Scope.APP,
        cache=providers.CacheSettings(finalizer=close_engine),
    )
    session = providers.Factory(
        create_session,
        scope=Scope.REQUEST,
        cache=providers.CacheSettings(finalizer=close_session),
    )


class Cache(Group):
    redis_client = providers.Factory(
        create_redis,
        scope=Scope.APP,
        cache=providers.CacheSettings(finalizer=close_redis),
    )


class Repositories(Group):
    # UserRepository signature: (session: AsyncSession)
    users = providers.Factory(UserRepository, scope=Scope.REQUEST)
    orders = providers.Factory(OrderRepository, scope=Scope.REQUEST)


class UseCases(Group):
    # PlaceOrder signature: (users: UserRepository, orders: OrderRepository, cache: aioredis.Redis)
    place_order = providers.Factory(PlaceOrder, scope=Scope.REQUEST)
    cancel_order = providers.Factory(CancelOrder, scope=Scope.REQUEST)


ALL_GROUPS = [Database, Cache, Repositories, UseCases]

container = Container(groups=ALL_GROUPS, validate=True)
```

`PlaceOrder` depends on providers from three different groups — `Repositories`, `Cache`, `Database` (transitively via the repositories). Nothing in `UseCases` references the other groups directly; type-based wiring sorts it out.

## Pitfalls

- **Duplicate `bound_type` raises at container creation.** If two groups register providers for the same type (e.g. both bind to `AsyncSession`), `Container(groups=[...])` raises `DuplicateProviderTypeError` immediately. Fix by assigning distinct types — e.g. declare thin subclasses (`class WriteSession(AsyncSession): ...`) — or set `bound_type=None` on one provider and wire it explicitly via `kwargs`. See [Duplicate provider type](../troubleshooting/duplicate-type-error.md).
- **Attribute-name collisions do not affect `Container`.** `Container` keys providers on their `bound_type`, not on the attribute name. Two groups can both have an attribute named `session` as long as their `bound_type`s differ — `Container` sees no conflict. The duplicate-name `ValueError` belongs to `modern-di-pytest`'s `expose(*groups)` helper (a separate package), which generates one pytest fixture per attribute name and does raise `ValueError` on duplicates. If you use `expose()`, ensure attribute names are unique across the groups you pass to it.
- **Order in `groups=[...]` does not matter for resolution.** Validate at startup with `validate=True`.

## Auto-wiring with Litestar

If you're on Litestar, pass `autowired_groups=ALL_GROUPS` to `ModernDIPlugin` and every provider in those groups is automatically registered as a Litestar dependency by attribute name. Handlers can then declare `place_order: PlaceOrder` as a plain parameter — no per-route `FromDI`.

```python
from modern_di_litestar import ModernDIPlugin

app = Litestar(
    plugins=[ModernDIPlugin(container, autowired_groups=ALL_GROUPS)],
)
```

See the [Litestar integration](../integrations/litestar.md) for the full pattern.

## See also

- [Factories](../providers/factories.md), [Scopes](../providers/scopes.md).
- [Litestar integration](../integrations/litestar.md) — `autowired_groups`.
- [Async SQLAlchemy recipe](sqlalchemy.md) — the building blocks for the `Database` group above.
