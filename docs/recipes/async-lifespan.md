# Async resources via lifespan

**Problem.** A resource needs `await` to construct — a Redis pool, a Kafka producer, an authenticated HTTP client, anything that does I/O at startup. `modern-di` resolves synchronously, so the construction has to happen outside the resolve path.

## Solution

Do the async construction in the framework's lifespan. Use `container.set_context(SomeType, instance)` to register the live object on the APP container, then declare a `ContextProvider(scope=Scope.APP, context_type=SomeType)` so downstream factories can depend on the type.

```python
import contextlib
from collections.abc import AsyncIterator

import fastapi
import redis.asyncio as aioredis
from modern_di import Container, Group, Scope, providers


class Dependencies(Group):
    redis_client = providers.ContextProvider(
        scope=Scope.APP,
        context_type=aioredis.Redis,
    )

    # Downstream factories declare `client: aioredis.Redis` and get the live instance
    cache = providers.Factory(
        scope=Scope.REQUEST,
        creator=CacheService,            # signature: (client: aioredis.Redis)
    )


container = Container(groups=[Dependencies], validate=True)


@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI) -> AsyncIterator[None]:
    async with container:                                          # ensures close_async on exit
        client = aioredis.Redis.from_url("redis://localhost")
        container.set_context(aioredis.Redis, client)
        try:
            yield
        finally:
            await client.aclose()


app = fastapi.FastAPI(lifespan=lifespan)
```

The same pattern works for Kafka producers, async HTTP clients with auth tokens, anything that needs `await` at startup.

## Pitfalls

- **Set context *before* yielding.** The lifespan hands control to the app inside the `yield`. If you `set_context` after yielding, requests that arrive in between won't see the value.
- **`set_context` does not propagate to existing children.** If you already built a REQUEST child container, calling `set_context` on the parent after the fact won't reach it. In the lifespan pattern above this is fine — child containers are created per request *after* lifespan startup completes.
- **Choose APP scope unless the resource is per-connection.** Redis/Kafka clients are process-singletons. For per-websocket-session resources, use `Scope.SESSION`.
- **`async with container:` handles APP-scope finalizers.** If you also registered a `CacheSettings(finalizer=...)` somewhere, this runs it on exit. Explicit `await client.aclose()` is for the lifespan-managed object that isn't wrapped by a Factory.

## When a sync creator works instead

Many async-flavored resources are actually constructed synchronously — `redis.asyncio.Redis.from_url(...)` and `sqlalchemy.ext.asyncio.create_async_engine(...)` both return without awaiting. For those, prefer a normal `Factory` with `cache_settings=CacheSettings(finalizer=async_close_fn)` and skip the lifespan + `set_context` dance entirely. Use this recipe only when construction genuinely requires `await`.

## See also

- [Lifecycle](../providers/lifecycle.md) — `close_async()` and finalizers.
- [Context Provider](../providers/context.md) — `ContextProvider` and `set_context` in depth.
- [Scopes](../providers/scopes.md) — APP vs SESSION vs REQUEST.
- [Async SQLAlchemy recipe](sqlalchemy.md) — the sync-creator-with-async-finalizer pattern for comparison.
