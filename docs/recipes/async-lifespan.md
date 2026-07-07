# Async resources via lifespan

**Problem.** A resource genuinely needs an `await` (or a running event loop) to construct — `aiohttp.ClientSession`, an `asyncpg` connection pool, an authenticated client whose construction does a token exchange. `modern-di` resolves synchronously, so the construction has to happen outside the resolve path.

## Solution

Do the async construction in the framework's lifespan. Use `container.set_context(SomeType, instance)` to register the live object on the APP container, then declare a `ContextProvider(scope=Scope.APP, context_type=SomeType)` so downstream factories can depend on the type.

```python
import contextlib
from collections.abc import AsyncIterator

import aiohttp
import fastapi
from modern_di import Container, Group, Scope, providers


class Dependencies(Group):
    http_client = providers.ContextProvider(
        scope=Scope.APP,
        context_type=aiohttp.ClientSession,
    )

    # Downstream factories declare `client: aiohttp.ClientSession` and get the live instance
    weather_api = providers.Factory(
        scope=Scope.REQUEST,
        creator=WeatherApi,            # signature: (client: aiohttp.ClientSession)
    )


container = Container(groups=[Dependencies], validate=True)


@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI) -> AsyncIterator[None]:
    async with container:                                          # ensures close_async on exit
        async with aiohttp.ClientSession() as session:             # must be inside running loop
            container.set_context(aiohttp.ClientSession, session)
            yield
        # ClientSession is closed by `async with` here


app = fastapi.FastAPI(lifespan=lifespan)
```

`aiohttp.ClientSession` captures the running event loop at construction time, so it has to be built inside an async context — which the lifespan provides.

The same pattern works for `asyncpg.create_pool(...)` (truly async), authenticated API clients that do a token exchange at startup, or anything else that needs `await` to be ready.

`asyncpg.create_pool(...)` returns an awaitable `Pool` that only opens its
connections when `await`ed (or entered with `async with`); modern-di has async
*finalizers* but no async *initializer*, so the `await` has to happen in the
lifespan.

## Pitfalls

- **Set context *before* yielding.** The lifespan hands control to the app inside the `yield`. If you `set_context` after yielding, requests that arrive in between won't see the value.
- **`set_context` never propagates between containers** — see [context propagation](../providers/context.md#context-propagation). In the lifespan pattern above this is fine — the resource is APP-scoped, so the APP-scoped `ContextProvider` reads the value set on the APP container; per-request context is passed to each REQUEST child via `build_child_container(context={...})`.
- **Combining a hand-written lifespan with an integration's `setup_di`.** The integration (e.g. [`modern-di-fastapi`](../integrations/fastapi.md)'s `setup_di(app, container)`) already appends a lifespan that closes the container, and it merges with any `lifespan=` you pass. Keep the resource setup in your lifespan but drop the `async with container` wrapper — the integration owns the container close, and wrapping both closes it twice.
- **Choose APP scope unless the resource is per-connection.** Redis/Kafka clients are process-singletons. For per-websocket-session resources, use `Scope.SESSION`.
- **`async with container:` handles APP-scope finalizers.** If you also registered a `CacheSettings(finalizer=...)` somewhere, this runs it on exit. The lifespan-managed object isn't wrapped by a Factory, so its cleanup (`async with aiohttp.ClientSession()` in the example) is on you.

## When a sync creator works instead

Many "async" resources actually construct synchronously — `redis.asyncio.Redis.from_url(...)`, `sqlalchemy.ext.asyncio.create_async_engine(...)`, and `httpx.AsyncClient(...)` all return without awaiting. For those, prefer a normal `Factory` with `cache=CacheSettings(finalizer=async_close_fn)` and skip the lifespan + `set_context` dance entirely. Use this recipe only when construction genuinely needs `await` or a running event loop.

## See also

- [Lifecycle](../providers/lifecycle.md) — `close_async()` and finalizers.
- [Context Provider](../providers/context.md) — `ContextProvider` and `set_context` in depth.
- [Scopes](../providers/scopes.md) — APP vs SESSION vs REQUEST.
- [Async SQLAlchemy recipe](sqlalchemy.md) — the sync-creator-with-async-finalizer pattern for comparison.
