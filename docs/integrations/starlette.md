# Usage with `Starlette`

Starlette has no dependency-injection system of its own, so `modern-di-starlette`
uses the `@inject` decorator with `FromDI` markers (there is no `Depends`).
`setup_di` composes the lifespan and installs middleware that opens a
per-connection child container automatically.

## How to use

### 1. Install `modern-di-starlette`

=== "uv"

      ```bash
      uv add modern-di-starlette
      ```

=== "pip"

      ```bash
      pip install modern-di-starlette
      ```

### 2. Apply to your application

```python
import dataclasses
import typing

from modern_di import Container, Group, Scope, providers
from modern_di_starlette import FromDI, inject, setup_di
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


@dataclasses.dataclass(kw_only=True)
class Settings:
    debug: bool = True


class AppGroup(Group):
    settings = providers.Factory(scope=Scope.APP, creator=Settings)


@inject
async def homepage(
    request: Request,
    settings: typing.Annotated[Settings, FromDI(AppGroup.settings)],
) -> JSONResponse:
    return JSONResponse({"debug": settings.debug})


app = Starlette(routes=[Route("/", homepage)])
setup_di(app, Container(groups=[AppGroup], validate=True))
```

### 3. Scopes

An HTTP request opens a `Scope.REQUEST` child container; a WebSocket connection
opens a `Scope.SESSION` one. Providers resolve from the connection's child
container, so `Scope.REQUEST` providers live for exactly one request.
