# Organize a large container with multiple Groups

**Problem.** Your service has 30+ providers and stuffing them all into one `Group` is unreadable.

## Solution

Split providers into multiple `Group` subclasses by domain — database, cache, messaging, use cases — and pass them all to `Container(groups=[...])`. Cross-group dependencies wire by type, with no explicit references between groups.

```python
from modern_di import Container, Group, Scope, providers


# Infrastructure: database
class Database(Group):
    engine = providers.Factory(
        scope=Scope.APP,
        creator=create_engine,
        cache_settings=providers.CacheSettings(finalizer=close_engine),
    )
    session = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_session,
        cache_settings=providers.CacheSettings(finalizer=close_session),
    )


# Infrastructure: cache
class Cache(Group):
    redis_client = providers.Factory(
        scope=Scope.APP,
        creator=create_redis,
        cache_settings=providers.CacheSettings(finalizer=close_redis),
    )


# Domain
class Repositories(Group):
    users = providers.Factory(scope=Scope.REQUEST, creator=UserRepository)
    orders = providers.Factory(scope=Scope.REQUEST, creator=OrderRepository)


class UseCases(Group):
    # PlaceOrder signature: (users: UserRepository, orders: OrderRepository, cache: redis.asyncio.Redis)
    place_order = providers.Factory(scope=Scope.REQUEST, creator=PlaceOrder)
    cancel_order = providers.Factory(scope=Scope.REQUEST, creator=CancelOrder)


ALL_GROUPS = [Database, Cache, Repositories, UseCases]

container = Container(groups=ALL_GROUPS, validate=True)
```

`PlaceOrder` depends on providers from three different groups — `Repositories`, `Cache`, `Database` (transitively via the repositories). Nothing in `UseCases` references the other groups directly; type-based wiring sorts it out.

## Pitfalls

- **Name collisions raise at container creation.** If two groups define an attribute with the same name (`Cache.session` and `Database.session`), you get `ValueError`. Rename one — `database_session` and `cache_session`, for example.
- **Type collisions are silent.** If two groups both register providers for `AsyncSession` with different return types, the second registration wins. Use distinct types (or `bound_type=` on the second) when you genuinely need both.
- **Order in `groups=[...]` does not matter for resolution.** It only matters for the silent-shadow case above. Validate at startup.

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
