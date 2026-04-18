# modern-di — Core Concepts

## Scope hierarchy

```python
from modern_di import Scope
# IntEnum: APP=1, SESSION=2, REQUEST=3, ACTION=4, STEP=5
```

A provider at scope N can only depend on providers at scopes 1..N. Higher number = more short-lived.
Typical split: `APP` for singletons, `REQUEST` for per-HTTP-request objects.

WebSocket handlers use `SESSION` scope instead of `REQUEST`.

## Group — provider namespace

`Group` is a non-instantiable class. Declare providers as class attributes:

```python
from modern_di import Group, Scope, providers

class Dependencies(Group):
    db_engine = providers.Factory(
        scope=Scope.APP,
        creator=create_async_engine,
        cache_settings=providers.CacheSettings(finalizer=close_engine),
    )
    session = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_session,
        cache_settings=providers.CacheSettings(finalizer=close_session),
    )
    users_repo = providers.Factory(
        scope=Scope.REQUEST,
        creator=UsersRepository,
        kwargs={"session": session},   # explicit reference; auto-wiring works when type is unambiguous
    )
```

## Factory — the main provider type

```python
providers.Factory(
    scope=Scope.APP,              # default is Scope.APP
    creator=MyClass,              # any callable; return type inferred from annotation
    bound_type=None,              # override if auto-inference is wrong; set to None to exclude from registry
    kwargs={"key": "value"},      # static overrides that bypass type-based resolution
    cache_settings=providers.CacheSettings(...),  # enables caching (singleton pattern)
    skip_creator_parsing=False,   # set True for lambdas or C-extension callables
)
```

**Auto-wiring**: at declaration time, `Factory` inspects the creator's type hints. At resolution, it
finds matching providers by type and resolves them recursively. Explicit `kwargs` override this.

**Singleton pattern** — there is no separate `Singleton` class:
```python
providers.Factory(
    creator=MyClass,
    cache_settings=providers.CacheSettings(
        clear_cache=False,        # keep instance in cache after finalizer runs (default True)
        finalizer=my_cleanup,     # sync or async — auto-detected
    ),
)
```

## Container

```python
from modern_di import Container

# Root container — create once at app startup
app_container = Container(scope=Scope.APP, groups=[Dependencies])

# Per-request child container — own cache, shares providers and overrides with parent
request_container = app_container.build_child_container(scope=Scope.REQUEST)

# Resolve by type (any matching provider in registry)
instance = request_container.resolve(UsersRepository)

# Resolve by provider reference — preferred, unambiguous
instance = request_container.resolve_provider(Dependencies.users_repo)

# Cleanup — calls finalizers for all cached instances at this scope
await request_container.close_async()   # or .close_sync() for sync apps
```

## ContextProvider — injecting runtime values

For values that only exist at runtime (e.g. the HTTP request object):

```python
class Dependencies(Group):
    http_request = providers.ContextProvider(scope=Scope.REQUEST, context_type=Request)
```

Pass the value when building the child container:
```python
child = app_container.build_child_container(
    scope=Scope.REQUEST,
    context={Request: actual_request_object},
)
```

Framework integrations (modern-di-litestar, modern-di-fastapi) do this automatically for
`litestar.Request` / `fastapi.Request`.

## SQLAlchemy factory pattern

This pattern is identical in both Litestar and FastAPI templates:

```python
# app/resources/db.py
from sqlalchemy.ext import asyncio as sa

def create_sa_engine() -> sa.AsyncEngine:
    return sa.create_async_engine(url=DATABASE_URL, pool_size=10, pool_pre_ping=True)

async def close_sa_engine(engine: sa.AsyncEngine) -> None:
    await engine.dispose()

def create_session(engine: sa.AsyncEngine) -> sa.AsyncSession:
    return sa.AsyncSession(engine, expire_on_commit=False, autoflush=False)

async def close_session(session: sa.AsyncSession) -> None:
    await session.close()
```

```python
# app/ioc.py
from modern_di import Group, Scope, providers
from app.resources.db import close_sa_engine, close_session, create_sa_engine, create_session

class Dependencies(Group):
    database_engine = providers.Factory(
        creator=create_sa_engine,
        cache_settings=providers.CacheSettings(finalizer=close_sa_engine),
    )
    session = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_session,
        cache_settings=providers.CacheSettings(finalizer=close_session),
    )
    users_repository = providers.Factory(
        scope=Scope.REQUEST,
        creator=UsersRepository,
        kwargs={"session": session},
    )
```

## Key design rules

- **No global state** — pass the Container explicitly (via `app.state` or framework plugin).
- **Resolution is synchronous** — `container.resolve()` is not awaitable. Async creators are supported;
  the framework integration awaits them.
- **`skip_creator_parsing=True`** — use for lambdas or C-extension callables. Combine with explicit `kwargs`.
- **`container_provider`** — the Container itself is auto-registered, so any class with
  `__init__(self, container: Container)` is auto-wired.
