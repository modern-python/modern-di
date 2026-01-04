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
    singleton = providers.Singleton(Scope.APP, create_singleton)


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
