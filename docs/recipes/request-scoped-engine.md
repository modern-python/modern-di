# Request-scoped engine selection (read replicas)

> **Advanced.** Use this only if you have actual read-replica traffic to route. For a single-database setup, the [Async SQLAlchemy recipe](sqlalchemy.md) is what you want.

**Problem.** Route read-only requests (`GET`, `HEAD`) to a read-replica engine and mutating requests to the primary, without changing handler code.

## Solution

Two APP-scoped engine factories — primary and replica — and one REQUEST-scoped factory that inspects the request and returns the engine to use for it. Sessions and repositories depend on the *request-scoped* engine, not the named factories.

```python
import sqlalchemy.ext.asyncio as sa_async
import fastapi
from modern_di import Group, Scope, providers


def create_primary_engine() -> sa_async.AsyncEngine:
    return sa_async.create_async_engine("postgresql+asyncpg://primary/db")


def create_replica_engine() -> sa_async.AsyncEngine:
    return sa_async.create_async_engine("postgresql+asyncpg://replica/db")


async def close_engine(engine: sa_async.AsyncEngine) -> None:
    await engine.dispose()


# Choose which engine this request uses.
# `primary` and `replica` are injected by name from kwargs.
# `request` is injected by type from the framework's request ContextProvider.
def choose_engine(
    primary: sa_async.AsyncEngine,
    replica: sa_async.AsyncEngine,
    request: fastapi.Request,
) -> sa_async.AsyncEngine:
    if request.method in ("GET", "HEAD"):
        return replica
    return primary


class PrimaryEngine(sa_async.AsyncEngine): ...
class ReplicaEngine(sa_async.AsyncEngine): ...


class Dependencies(Group):
    primary = providers.Factory(
        scope=Scope.APP,
        creator=create_primary_engine,
        bound_type=PrimaryEngine,
        cache=providers.CacheSettings(finalizer=close_engine),
    )
    replica = providers.Factory(
        scope=Scope.APP,
        creator=create_replica_engine,
        bound_type=ReplicaEngine,
        cache=providers.CacheSettings(finalizer=close_engine),
    )

    # REQUEST-scope: picks per-request, cached for the rest of that request
    engine = providers.Factory(
        scope=Scope.REQUEST,
        creator=choose_engine,
        kwargs={"primary": primary, "replica": replica},
        cache=True,
    )

    # Sessions and repositories use the REQUEST-scoped engine
    session = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_session,
        cache=providers.CacheSettings(finalizer=close_session),
    )
```

Why the `PrimaryEngine` / `ReplicaEngine` subclasses: type-based resolution needs distinct types for the two factories. Without them, both would register under `AsyncEngine` and `Container(groups=[...])` would raise `DuplicateProviderTypeError` at startup. See [Duplicate provider type](../troubleshooting/duplicate-type-error.md).

## Pitfalls

- **The choice factory must be REQUEST-scoped.** It depends on the per-request `Request` object — an APP-scoped factory cannot consume request-scoped data and `validate=True` will reject it.
- **The framework integration provides `fastapi.Request` (or `litestar.Request`) automatically.** No need to declare a `ContextProvider` for it. For Litestar, use `litestar.Request`.
- **Don't apply this to per-connection pooling decisions.** Engines (and their pools) are APP-scoped — the choice you make per request just selects which long-lived pool the session checks out from. Trying to make the engine itself REQUEST-scoped would create and dispose a pool every request.
- **Watch for write-after-read in a single request.** If a `GET` handler ends up doing a write (e.g. updating a `last_seen_at` field), it'll go to the replica and fail. Either move the side-effect out of the read path, or pick a different routing predicate than HTTP method.

## See also

- [Async SQLAlchemy recipe](sqlalchemy.md) — the simpler single-engine pattern.
- [Context Provider](../providers/context.md) — how `Request` is injected.
- [Scopes](../providers/scopes.md) — why the engines are APP but the choice is REQUEST.
