# Async resources via lifespan

Some resources need an `await` or a running event loop to construct: `aiohttp.ClientSession`, an `asyncpg` connection pool, or a client that exchanges a token at startup. `modern-di` resolves synchronously, so a creator cannot `await`. Build these resources in the framework's lifespan and hand the live object to the container.

## Solution

In the lifespan, build the resource and register it on the APP container with `container.set_context(SomeType, instance)`. Declare a `ContextProvider(SomeType, scope=Scope.APP)` so other factories can depend on the type. With FastAPI:

```python
import contextlib
import dataclasses
from collections.abc import AsyncIterator

import aiohttp
import fastapi
import modern_di_fastapi
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass
class WeatherApi:
    client: aiohttp.ClientSession

    async def forecast(self, city: str) -> dict[str, str]:
        async with self.client.get(f"https://weather.example.com/{city}") as response:
            return await response.json()


class Dependencies(Group):
    http_client = providers.ContextProvider(aiohttp.ClientSession, scope=Scope.APP)
    weather_api = providers.Factory(WeatherApi, scope=Scope.REQUEST)


container = Container(groups=[Dependencies])


@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI) -> AsyncIterator[None]:
    async with aiohttp.ClientSession() as session:
        container.set_context(aiohttp.ClientSession, session)
        yield


app = fastapi.FastAPI(lifespan=lifespan)
modern_di_fastapi.setup_di(app, container)
container.validate()


@app.get("/forecast/{city}")
async def forecast(
    city: str,
    weather_api: WeatherApi = modern_di_fastapi.FromDI(WeatherApi),
) -> dict[str, str]:
    return await weather_api.forecast(city)
```

<!-- invisible-code-block: python
from fastapi.testclient import TestClient


@app.get("/client-open")
async def client_open(weather_api: WeatherApi = modern_di_fastapi.FromDI(WeatherApi)) -> bool:
    return not weather_api.client.closed


with TestClient(app) as client:
    assert client.get("/client-open").json() is True
-->

`WeatherApi` receives the session through its `client: aiohttp.ClientSession` annotation. `aiohttp.ClientSession` needs a running event loop when it is constructed, and the lifespan runs inside the application's loop.

`setup_di` wraps your lifespan. Since modern-di-fastapi 4.2.0, the container is the outer context: it opens before your lifespan's startup code and closes after your `async with` block exits. APP-scoped finalizers therefore run after the session has closed. If one of them needs the session, pass `manage_lifespan=False` to `setup_di` and enter the container yourself, as below.

Without an integration, or with `manage_lifespan=False`, enter the container yourself, after the resource, so it closes first:

```python
import contextlib
from collections.abc import AsyncIterator

import aiohttp
import fastapi


@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI) -> AsyncIterator[None]:
    async with aiohttp.ClientSession() as session, container:
        container.set_context(aiohttp.ClientSession, session)
        yield
```

<!-- invisible-code-block: python
import fastapi
from modern_di import Scope

async with lifespan(fastapi.FastAPI()):
    request_container = container.build_child_container(scope=Scope.REQUEST)
    assert not request_container.resolve(WeatherApi).client.closed
assert container.closed
-->

The same pattern fits `asyncpg.create_pool(...)`, which returns a pool that opens its connections only when awaited, and any client that needs an `await` before it is ready. `modern-di` has async finalizers but no async initializer, so that `await` belongs in the lifespan.

## Pitfalls

- `set_context` never propagates between containers; see [Context propagation](../providers/context.md#context-propagation). Here that is fine: the `ContextProvider` is APP-scoped and the value is set on the APP container, so every REQUEST child reaches it.
- Give the container one owner. With `setup_di` at the default `manage_lifespan=True`, the integration opens and closes it, so don't also enter `async with container:` in the lifespan. To own the close yourself, pass `manage_lifespan=False`.
- The container does not own the lifespan's resource. It was never created by a `Factory`, so no finalizer closes it; the `async with aiohttp.ClientSession()` block does.

## When a sync creator works instead

Many async clients construct synchronously: `redis.asyncio.Redis.from_url(...)`, `sqlalchemy.ext.asyncio.create_async_engine(...)` and `httpx.AsyncClient(...)` all return without awaiting. For those, use a plain `Factory` with `cache=CacheSettings(finalizer=...)` and an async finalizer, and skip the lifespan and `set_context`. Use this recipe only when construction needs `await` or a running event loop.

## See also

- [Lifecycle](../providers/lifecycle.md): `close_async()` and finalizers.
- [Context providers](../providers/context.md): `ContextProvider` and `set_context` in depth.
- [Scopes](../providers/scopes.md): APP vs SESSION vs REQUEST.
- [Async SQLAlchemy recipe](sqlalchemy.md): the sync-creator-with-async-finalizer pattern for comparison.
