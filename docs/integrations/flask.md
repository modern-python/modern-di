# Usage with `Flask`

Flask has no dependency-injection system of its own, so `modern-di-flask` uses
the `@inject` decorator with `FromDI` markers (there is no `Depends`). `setup_di`
installs a `before_request`/`teardown_appcontext` pair that opens a per-request
`Scope.REQUEST` child container and closes it once the request finishes.
Resolution is **sync-only** — the child container is closed with `close_sync()`.

## How to use

### 1. Install `modern-di-flask`

=== "uv"

      ```bash
      uv add modern-di-flask
      ```

=== "pip"

      ```bash
      pip install modern-di-flask
      ```

### 2. Apply to your application

```python
import typing

from flask import Flask
from modern_di import Container, Group, Scope, providers
from modern_di_flask import FromDI, inject, setup_di


class Settings:
    def __init__(self) -> None:
        self.greeting = "hello"


class Dependencies(Group):
    settings = providers.Factory(scope=Scope.APP, creator=Settings)


app = Flask(__name__)


@app.route("/hello/<name>")
@inject
def hello(name: str, settings: typing.Annotated[Settings, FromDI(Dependencies.settings)]) -> str:
    return f"{settings.greeting}, {name}"


# call setup_di AFTER registering routes — required when using auto_inject
setup_di(app, Container(groups=[Dependencies], validate=True))
```

`FromDI(dependency)` accepts either a provider reference (as above) or a plain
type, resolved from the per-request child container the middleware built.

### 3. `auto_inject`

Pass `auto_inject=True` to `setup_di` to wire every registered view (app routes
and blueprint routes alike) without a per-view `@inject`. Because it walks
`app.view_functions` at call time, `setup_di` must run **after** all routes —
including blueprint routes — have been registered:

```python
import typing

from flask import Flask
from modern_di import Container, Group, Scope, providers
from modern_di_flask import FromDI, setup_di


class Settings:
    def __init__(self) -> None:
        self.greeting = "hello"


class Dependencies(Group):
    settings = providers.Factory(scope=Scope.APP, creator=Settings)


app = Flask(__name__)


@app.route("/hello/<name>")
def hello(name: str, settings: typing.Annotated[Settings, FromDI(Dependencies.settings)]) -> str:
    return f"{settings.greeting}, {name}"


# no @inject needed on individual views
setup_di(app, Container(groups=[Dependencies], validate=True), auto_inject=True)
```

A view that already carries `@inject` is left alone — `auto_inject` only wraps
views that weren't injected yet.

### 4. Scopes and request lifecycle

See [the scope hierarchy](../providers/scopes.md#the-scope-dependency-rule).
Flask has no websocket concept, so the integration only ever opens one child
scope: `before_request` builds a `Scope.REQUEST` child of the root container
and stores it on `flask.g`; `teardown_appcontext` closes it with `close_sync()`
once the request (including error handling) is done.

### 5. Root container teardown

`setup_di` does not close the root container for you — Flask has no
application-shutdown hook to run it from. You own root teardown, typically at
your own process-shutdown point:

```python
from flask import Flask
from modern_di import Container, Group, Scope, providers
from modern_di_flask import fetch_di_container, setup_di


class Dependencies(Group):
    pass


app = Flask(__name__)
setup_di(app, Container(groups=[Dependencies], validate=True))

# ... register an atexit hook, a CLI teardown command, or call this
# explicitly wherever your process shuts down:
fetch_di_container(app).close_sync()
```

## Framework Context Objects

`flask.Request` is automatically made available by the integration — see
[Framework Context Objects](../providers/context.md#framework-context-objects)
for how implicit and explicit resolution work.

The following context provider is available for import:

- `flask_request_provider` — `ContextProvider` for the current `flask.Request` (REQUEST scope), auto-registered by type.

### Implicit Usage (Type-based Resolution)

```python
from flask import Request
from modern_di import Group, Scope, providers


def create_request_info(request: Request) -> dict[str, str]:
    return {"method": request.method, "url": request.url}


class AppGroup(Group):
    request_info = providers.Factory(create_request_info, scope=Scope.REQUEST)
```

### Explicit Usage (Provider-based Resolution)

```python
from flask import Request
from modern_di import Group, Scope, providers
from modern_di_flask import flask_request_provider


def create_request_info(request: Request) -> dict[str, str]:
    return {"method": request.method, "url": request.url}


class AppGroup(Group):
    request_info = providers.Factory(
        create_request_info,
        scope=Scope.REQUEST,
        kwargs={"request": flask_request_provider},
    )
```

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container, *, auto_inject=False)` | Registers the container on `app.extensions`, installs the `before_request`/`teardown_appcontext` pair that builds and closes a per-request `Scope.REQUEST` child container, and — if `auto_inject=True` — wraps every currently-registered view with `inject`; returns the container. |
| `FromDI(dependency)` | Marker (used with `@inject`) that resolves a provider or type from the per-request child container. |
| `inject` | Decorator for a view function; resolves its `FromDI`-annotated parameters without rewriting the function's signature. |
| `fetch_di_container(app)` | Returns the root `Container` stored on `app.extensions`. |
| `flask_request_provider` | `ContextProvider` for `flask.Request` (REQUEST scope), auto-registered by type. |
