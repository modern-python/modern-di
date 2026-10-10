# Async SQLAlchemy: engine, session, repository

This recipe wires `create_async_engine`, `AsyncSession` and repository classes through `modern-di`, so the process shares one engine, each request gets one session, and the containers close both.

## Solution

The recipe uses three providers at two scopes:

- The engine is at `Scope.APP`: cached, so the whole process shares one engine and its connection pool, and disposed when the APP container closes.
- The session is at `Scope.REQUEST`: cached in the request's container and closed when that container closes at the end of the request.
- Repositories are at `Scope.REQUEST` and uncached. Every resolve builds a new repository, and all the repositories in one request share its session.

```python
import sqlalchemy as sa
import sqlalchemy.ext.asyncio as sa_async
from modern_di import Group, Scope, providers


def create_engine() -> sa_async.AsyncEngine:
    return sa_async.create_async_engine(
        "postgresql+asyncpg://user:pass@localhost/db",
        pool_pre_ping=True,
    )


def create_session(engine: sa_async.AsyncEngine) -> sa_async.AsyncSession:
    return sa_async.AsyncSession(engine, expire_on_commit=False)


class UserRepository:
    def __init__(self, session: sa_async.AsyncSession) -> None:
        self.session = session

    async def count(self) -> int:
        return await self.session.scalar(sa.text("SELECT count(*) FROM users"))


class Dependencies(Group):
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
    user_repository = providers.Factory(
        UserRepository,
        scope=Scope.REQUEST,
    )
```

`create_session` receives the engine through its `sa_async.AsyncEngine` annotation, and `UserRepository` receives the session through its `sa_async.AsyncSession` annotation, so no `kwargs` are needed. Both finalizers are unbound async methods: Python passes the cached instance as `self`, as [Caching and finalizers](../providers/lifecycle.md#caching-and-finalizers) explains.

Wire the container to your framework and inject the repository where a handler needs it. With FastAPI:

```python
import fastapi
import modern_di_fastapi
from modern_di import Container


container = Container(groups=[Dependencies])

app = fastapi.FastAPI()
modern_di_fastapi.setup_di(app, container)
container.validate()


@app.get("/users/count")
async def count_users(
    repository: UserRepository = modern_di_fastapi.FromDI(UserRepository),
) -> int:
    return await repository.count()
```

For a route that uses `FromDI`, `modern-di-fastapi` builds a REQUEST child container, resolves the session and the repository from it, and closes it after the response, which closes the session. The engine is disposed when the application shuts down. Call `container.validate()` after `setup_di`, because `setup_di` registers the integration's own providers; see [Validation](../providers/lifecycle.md#validation).

## Pitfalls

- Keep `expire_on_commit=False`. With the default `True`, a commit expires every loaded object, and the next attribute read tries to reload it. In async code that read fails with a `StatementError` wrapping `sqlalchemy.exc.MissingGreenlet`.
- The engine's finalizer is async, so the APP container has to be closed with `close_async()`. FastAPI and Litestar do that at shutdown. Flask, gRPC and Typer leave the APP container to you, and Celery closes it with `close_sync()`, which cannot await the finalizer. See [Per-scope finalization](../providers/lifecycle.md#per-scope-finalization) and [Async finalizers and `close_sync()`](../providers/lifecycle.md#async-finalizers-and-close_sync).
- Repositories hold a REQUEST-scoped session, so they cannot be APP-scoped. `container.validate()` rejects an APP-scoped repository; see [the scope dependency rule](../providers/scopes.md#the-scope-dependency-rule).

## Variations

- For several databases, declare one engine and one session factory per database. Two providers cannot both register under `AsyncEngine`, so give the extra ones `bound_type=None` and pass them to their consumers through [`kwargs`](../providers/factories.md#kwargs). [Request-scoped engine selection](request-scoped-engine.md) shows the pattern with a primary and a replica.
- In tests, override the engine with a connection inside a transaction that rolls back after each test. See [Transactional database tests](testing-overrides.md#transactional-database-tests).

## See also

- [Lifecycle](../providers/lifecycle.md): finalizers and `close_async()`.
- [Scopes](../providers/scopes.md): why the engine is APP and sessions are REQUEST.
- [Litestar integration](../integrations/litestar.md), [FastAPI integration](../integrations/fastapi.md).
- Reference templates: [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template), [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template).
