# Usage with `FastAPI`

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
from modern_di import Container, Group, Scope, providers


app = fastapi.FastAPI()


def create_singleton() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


class AppGroup(Group):
    singleton = providers.Factory(
        scope=Scope.APP,
        creator=create_singleton,
        cache_settings=providers.CacheSettings()
    )


# Register your groups
ALL_GROUPS = [AppGroup]

# Setup DI with your groups
modern_di_fastapi.setup_di(app, Container(groups=ALL_GROUPS))


@app.get("/")
async def read_root(
    instance: typing.Annotated[
        datetime.datetime,
        modern_di_fastapi.FromDI(datetime.datetime),  # Resolve by type instead of provider
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
    request_container = session_container.build_child_container(scope=modern_di.Scope.REQUEST)
    # REQUEST scope is entered here
    # You can resolve dependencies here
    pass

    await websocket.accept()
    await websocket.send_text("test")
    await websocket.close()
```

## Framework Context Objects

Framework-specific context objects like `fastapi.Request` and `fastapi.WebSocket` are automatically provided by the integration, so you don't need to explicitly define ContextProviders for these objects in your dependency groups.

For example, to use the request object in a factory:

```python
import fastapi
from modern_di import Group, Scope, providers


def create_request_info(request: fastapi.Request) -> dict[str, str]:
    return {
        "method": request.method,
        "url": str(request.url),
        "timestamp": "2023-01-01T00:00:00Z"
    }


class AppGroup(Group):
    # Factory uses the request from context (automatically provided by the integration)
    request_info = providers.Factory(
        scope=Scope.REQUEST,
        creator=create_request_info,
    )
```
