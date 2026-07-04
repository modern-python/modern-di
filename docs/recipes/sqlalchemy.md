# Async SQLAlchemy: engine, session, repository

**Problem.** Wire `create_async_engine` + `AsyncSession` + repository classes through `modern-di` so the engine is shared process-wide, sessions are per-request, and cleanup happens automatically at shutdown and at the end of each request.

## Solution

Three providers, three scopes:

- **Engine** at `Scope.APP` — one per process, cached, disposed at shutdown.
- **Session** at `Scope.REQUEST` — one per request, cached inside that request, closed at the end of the request.
- **Repositories** at `Scope.REQUEST` — depend on the session by type; one per request.

```python
import sqlalchemy.ext.asyncio as sa_async
from modern_di import Group, Scope, providers


def create_engine() -> sa_async.AsyncEngine:
    return sa_async.create_async_engine(
        "postgresql+asyncpg://user:pass@localhost/db",
        pool_pre_ping=True,
    )


async def close_engine(engine: sa_async.AsyncEngine) -> None:
    await engine.dispose()


def create_session(engine: sa_async.AsyncEngine) -> sa_async.AsyncSession:
    return sa_async.AsyncSession(engine, expire_on_commit=False)


async def close_session(session: sa_async.AsyncSession) -> None:
    await session.close()


class UserRepository:
    def __init__(self, session: sa_async.AsyncSession) -> None:
        self.session = session


class Dependencies(Group):
    engine = providers.Factory(
        scope=Scope.APP,
        creator=create_engine,
        cache=providers.CacheSettings(finalizer=close_engine),
    )
    session = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_session,
        cache=providers.CacheSettings(finalizer=close_session),
    )
    user_repository = providers.Factory(
        scope=Scope.REQUEST,
        creator=UserRepository,
    )
```

The session factory consumes `engine: sa_async.AsyncEngine` via type-based wiring — no `kwargs={}` needed. `UserRepository` consumes `session: sa_async.AsyncSession` the same way.

Wire to your framework as usual:

```python
import fastapi
import modern_di_fastapi
from modern_di import Container


container = Container(groups=[Dependencies], validate=True)

app = fastapi.FastAPI()
modern_di_fastapi.setup_di(app, container)
```

The integration creates a REQUEST child container per request, so the session and repository are created on first resolve and cleaned up when the request ends.

## Pitfalls

- **`CacheSettings.finalizer` accepts sync or async functions** — it auto-detects. Don't wrap with `asyncio.run` or `asyncio.ensure_future`.
- **`expire_on_commit=False`** on `AsyncSession` avoids expensive refreshes after commit. If you rely on `expire_on_commit=True`, leave it — but it's a common source of "session is closed" errors in async code.
- **Don't share the engine across REQUEST containers manually.** The provider already does it: REQUEST containers walk up to the APP container to resolve the engine.
- **Repositories must be REQUEST-scoped**, not APP-scoped — they hold a session which is REQUEST-scoped, and `validate=True` will reject the inverse.

## Variations

- **Multiple databases.** Declare two engine factories, two session factories, and give the second set distinct return types or `bound_type=` arguments so type-based resolution can tell them apart.
- **Test connections.** Tests typically override the engine with an `AsyncConnection` inside a transaction — see [Testing with overrides](testing-overrides.md).

## See also

- [Lifecycle](../providers/lifecycle.md) — finalizers and `close_async()`.
- [Scopes](../providers/scopes.md) — why the engine is APP and sessions are REQUEST.
- [Litestar integration](../integrations/litestar.md), [FastAPI integration](../integrations/fastapi.md).
- Reference templates: [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template), [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template).
