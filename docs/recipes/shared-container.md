# FastAPI and FastStream sharing a container

An HTTP API and a message consumer that run in one process can share one container, so both get
the same APP-scoped instances, such as one connection pool. By default each integration opens the
root container at startup and closes it at shutdown, so the first app to stop closes it under the
other. Pass `manage_lifespan=False` to both `setup_di` calls and open and close the container
yourself. The flag needs modern-di-fastapi 4.1.0 and modern-di-faststream 4.1.0 or later.

## Setup

```python
import dataclasses
import typing

import fastapi
import faststream
import modern_di_fastapi
import modern_di_faststream
from faststream.nats import NatsBroker
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class ConnectionPool:
    closed: bool = False

    async def close(self) -> None:
        self.closed = True


class Dependencies(Group):
    pool = providers.Factory(
        ConnectionPool, scope=Scope.APP, cache=providers.CacheSettings(finalizer=ConnectionPool.close)
    )


container = Container(groups=[Dependencies])

app = fastapi.FastAPI()
modern_di_fastapi.setup_di(app, container, manage_lifespan=False)

broker = NatsBroker()
stream = faststream.FastStream(broker)
modern_di_faststream.setup_di(stream, container, manage_lifespan=False)
container.validate()


@app.get("/pool")
async def pool_status(
    pool: typing.Annotated[ConnectionPool, modern_di_fastapi.FromDI(ConnectionPool)],
) -> dict[str, bool]:
    return {"closed": pool.closed}


@broker.subscriber("orders")
async def handle_order(
    pool: typing.Annotated[ConnectionPool, modern_di_faststream.FromDI(ConnectionPool)],
) -> dict[str, bool]:
    return {"closed": pool.closed}
```

With the flag off, each integration still registers its context providers and builds a child
container for every request or message. Only the root is left to you.

## Running the apps side by side

Run the uvicorn server and the FastStream app in one `asyncio.gather`, inside
`async with container:`:

```python
import asyncio

import uvicorn


async def main() -> None:
    server = uvicorn.Server(uvicorn.Config(app))
    async with container:
        await asyncio.gather(stream.run(), server.serve())


if __name__ == "__main__":
    asyncio.run(main())
```

<!-- invisible-code-block: python
import warnings

from faststream import TestApp
from faststream.nats import TestNatsBroker

with warnings.catch_warnings():
    warnings.simplefilter("ignore")  # starlette warns when httpx2 is not installed
    from fastapi.testclient import TestClient


async def run_both() -> None:
    async with container:
        pool = container.resolve(ConnectionPool)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # TestNatsBroker cannot parse a Markdown file's AST
            async with TestNatsBroker(broker) as test_broker, TestApp(stream):
                response = await test_broker.request({}, "orders")
                assert await response.decode() == {"closed": False}
        assert not container.closed
        with TestClient(app) as client:
            assert client.get("/pool").json() == {"closed": False}
        assert not container.closed
    assert container.closed
    assert pool.closed


await run_both()
-->

Put `stream.run()` first. On SIGTERM uvicorn stops, puts back the signal handler it replaced at
startup, and raises the signal again, so FastStream stops after it. In the other order, FastStream's
handler replaces uvicorn's, and uvicorn keeps serving after FastStream has stopped.

The container closes when the `async with` block exits, after both apps have stopped. APP
finalizers run once, at that point.

## Starting FastStream inside the FastAPI lifespan

To run one uvicorn server, start the FastStream app from the FastAPI lifespan and enter the
container there, around `stream.start()` and `stream.stop()`:

<!-- invisible-code-block: python
import faststream
from faststream.nats import NatsBroker

container = Container(groups=[Dependencies])
broker = NatsBroker()
stream = faststream.FastStream(broker)


@broker.subscriber("orders")
async def handle_order(
    pool: typing.Annotated[ConnectionPool, modern_di_faststream.FromDI(ConnectionPool)],
) -> dict[str, bool]:
    return {"closed": pool.closed}
-->

```python
import contextlib
from collections.abc import AsyncIterator

import fastapi
import modern_di_fastapi
import modern_di_faststream


@contextlib.asynccontextmanager
async def lifespan(_: fastapi.FastAPI) -> AsyncIterator[None]:
    async with container:
        await stream.start()
        try:
            yield
        finally:
            await stream.stop()


app = fastapi.FastAPI(lifespan=lifespan)
app.add_api_route("/pool", pool_status)
modern_di_fastapi.setup_di(app, container, manage_lifespan=False)
modern_di_faststream.setup_di(stream, container, manage_lifespan=False)
```

<!-- invisible-code-block: python
from faststream.nats import TestNatsBroker


async def run_in_lifespan() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # TestNatsBroker cannot parse a Markdown file's AST
        async with TestNatsBroker(broker) as test_broker, app.router.lifespan_context(app):
            pool = container.resolve(ConnectionPool)
            response = await test_broker.request({}, "orders")
            assert await response.decode() == {"closed": False}
    assert container.closed
    assert pool.closed


await run_in_lifespan()
-->

The container closes after `stream.stop()` returns, so messages still in flight at shutdown resolve
from an open container. With the default flag, modern-di-fastapi would close the container inside
your lifespan, before `stream.stop()` runs.

## Pitfalls

- Set the flag on both integrations. One left at the default still closes the root when its app
  stops.
- With the flag off, nothing else closes the root. Without your `async with container:` block,
  APP finalizers never run.

## See also

- [Lifecycle](../providers/lifecycle.md#closing-and-reopening): what closing runs and what survives
  a reopen.
- [FastAPI](../integrations/fastapi.md) and [FastStream](../integrations/faststream.md): the two
  integrations.
- [ContainerClosedError](../troubleshooting/container-closed-error.md): the error a closed shared
  container raises.
