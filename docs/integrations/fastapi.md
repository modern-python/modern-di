# Usage with `Fastapi`

*More advanced example of usage with FastAPI - [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template)*

## How to use

1. Install `modern-di-fastapi`:

=== "uv"
 
      ```bash
      uv add modern-di-fastapi
      ```
 
=== "pip"

      ```bash
      pip install modern-di-fastapi
      ```

=== "poetry"

      ```bash
      poetry add modern-di-fastapi
      ```

2. Apply this code example to your application:
```python
import datetime
import contextlib
import typing

import fastapi
import modern_di_fastapi
from modern_di import Scope, providers


@contextlib.asynccontextmanager
async def lifespan_manager(app_: fastapi.FastAPI) -> typing.AsyncIterator[None]:
    async with modern_di_fastapi.fetch_di_container(app_):
        yield


app = fastapi.FastAPI(lifespan=lifespan_manager)
modern_di_fastapi.setup_di(app)


async def create_async_resource() -> typing.AsyncIterator[datetime.datetime]:
    # async resource initiated
    try:
        yield datetime.datetime.now(tz=datetime.timezone.utc)
    finally:
        pass  # async resource destructed


async_resource = providers.Resource(Scope.APP, create_async_resource)


@app.get("/")
async def read_root(
        instance: typing.Annotated[
            datetime.datetime,
            modern_di_fastapi.FromDI(async_resource),
        ],
) -> datetime.datetime:
    return instance

```

## Websockets

Usually our application uses only two scopes: `APP` and `REQUEST`.

But when websockets are used, `SESSION` scope is used as well:
- for the lifetime of websocket-connection we have `SESSION` scope
- for each message we have `REQUEST` scope

`APP` → `SESSION` → `REQUEST`

`SESSION` scope is entered automatically.
`REQUEST` scope must be entered manually:

```python
import typing

import fastapi
import modern_di
import modern_di_fastapi


app = fastapi.FastAPI()


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: fastapi.WebSocket,
    session_container: typing.Annotated[modern_di.Container, fastapi.Depends(modern_di_fastapi.build_di_container)],
) -> None:
    with session_container.build_child_container() as request_container:
        # REQUEST scope is entered here
        pass

    await websocket.accept()
    await websocket.send_text("test")
    await websocket.close()
```
