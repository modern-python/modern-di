# Request-scoped engine selection (read replicas)

> This is an advanced recipe. Use it only if you have actual read-replica traffic to route. For a single-database setup, use the [Async SQLAlchemy recipe](sqlalchemy.md).

This recipe routes read-only requests (`GET`, `HEAD`) to a read-replica engine and mutating requests to the primary, without changing handler code.

## Solution

Declare two APP-scoped engine factories, primary and replica, and one REQUEST-scoped factory that looks at the request and returns the engine to use for it. The session depends on that request-scoped engine by type.

```python
import fastapi
import modern_di_fastapi
import sqlalchemy.ext.asyncio as sa_async
from modern_di import Container, Group, Scope, providers


def create_primary_engine() -> sa_async.AsyncEngine:
    return sa_async.create_async_engine("postgresql+asyncpg://primary/db")


def create_replica_engine() -> sa_async.AsyncEngine:
    return sa_async.create_async_engine("postgresql+asyncpg://replica/db")


def choose_engine(
    primary: sa_async.AsyncEngine,
    replica: sa_async.AsyncEngine,
    request: fastapi.Request,
) -> sa_async.AsyncEngine:
    if request.method in ("GET", "HEAD"):
        return replica
    return primary


def create_session(engine: sa_async.AsyncEngine) -> sa_async.AsyncSession:
    return sa_async.AsyncSession(engine, expire_on_commit=False)


class Dependencies(Group):
    primary = providers.Factory(
        create_primary_engine,
        scope=Scope.APP,
        bound_type=None,
        cache=providers.CacheSettings(finalizer=sa_async.AsyncEngine.dispose),
    )
    replica = providers.Factory(
        create_replica_engine,
        scope=Scope.APP,
        bound_type=None,
        cache=providers.CacheSettings(finalizer=sa_async.AsyncEngine.dispose),
    )
    engine = providers.Factory(
        choose_engine,
        scope=Scope.REQUEST,
        kwargs={"primary": primary, "replica": replica},
        cache=True,
    )
    session = providers.Factory(
        create_session,
        scope=Scope.REQUEST,
        cache=providers.CacheSettings(finalizer=sa_async.AsyncSession.close),
    )


container = Container(groups=[Dependencies])

app = fastapi.FastAPI()
modern_di_fastapi.setup_di(app, container)
container.validate()


@app.api_route("/engine", methods=["GET", "POST"])
async def engine_url(
    session: sa_async.AsyncSession = modern_di_fastapi.FromDI(sa_async.AsyncSession),
) -> str:
    return str(session.bind.url)
```

<!-- invisible-code-block: python
from fastapi.testclient import TestClient

with TestClient(app) as client:
    assert client.get("/engine").json() == "postgresql+asyncpg://replica/db"
    assert client.post("/engine").json() == "postgresql+asyncpg://primary/db"
-->

Only `engine` is registered under `AsyncEngine`, so `create_session` gets the engine chosen for the request. Two providers cannot both register under one type, so `primary` and `replica` have `bound_type=None` and reach `choose_engine` through `kwargs`; see [`bound_type`](../providers/factories.md#bound_type). `request` is wired by type to the `fastapi.Request` the integration puts in each request's container.

## Pitfalls

- The choice factory must be REQUEST-scoped, because it consumes the per-request `Request`. `container.validate()` rejects an APP-scoped one with `InvalidScopeDependencyError`.
- The integration registers the `ContextProvider` for `fastapi.Request` (on Litestar, `litestar.Request`), so you don't declare one. It does so in `setup_di`, so call `container.validate()` after `setup_di`, as above; see [Framework context objects](../providers/context.md#framework-context-objects).
- `kwargs` resolves both engines every time `choose_engine` runs, so the first request creates both and they stay cached, even though it uses one of them. `create_async_engine` opens no connection, so this costs nothing until a session checks one out.
- Keep the engines APP-scoped. Each engine owns a connection pool, and the per-request choice only selects which long-lived pool the session uses. A REQUEST-scoped engine would build and dispose a pool on every request.
- Watch for writes in a read request. If a `GET` handler writes (updating a `last_seen_at` column, say), the write goes to the replica and fails. Move the side effect out of the read path, or route on something other than the HTTP method.

## See also

- [Async SQLAlchemy recipe](sqlalchemy.md): the simpler single-engine pattern.
- [Context providers](../providers/context.md): how `Request` is injected.
- [Scopes](../providers/scopes.md): why the engines are APP but the choice is REQUEST.
