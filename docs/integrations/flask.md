# Usage with `Flask`

Flask has no dependency injection of its own, so `modern-di-flask` provides an `@inject` decorator
that fills the view parameters marked with `FromDI`. `setup_di` installs a
`before_request`/`teardown_appcontext` pair that gives each request a `Scope.REQUEST` child
container and closes it with `close_sync()` once the request finishes. Resolution is sync-only,
and views must be sync too: `@inject` on an `async def` view hands Flask a coroutine, and the
request fails with `TypeError`.

## Installation

=== "uv"

    ```bash
    uv add modern-di-flask
    ```

=== "pip"

    ```bash
    pip install modern-di-flask
    ```

=== "poetry"

    ```bash
    poetry add modern-di-flask
    ```

## Usage

```python
import dataclasses
import typing

from flask import Flask
from modern_di import Container, Group, Scope, providers
from modern_di_flask import FromDI, inject, setup_di


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    service_name: str = "catalog"


@dataclasses.dataclass(kw_only=True, slots=True)
class Report:
    settings: Settings   # APP-scoped, injected by type

    def as_dict(self) -> dict[str, str]:
        return {"service": self.settings.service_name}


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    report = providers.Factory(Report, scope=Scope.REQUEST)


app = Flask(__name__)


@app.route("/report")
@inject
def get_report(report: typing.Annotated[Report, FromDI(Report)]) -> dict[str, str]:
    return report.as_dict()


container = Container(groups=[AppGroup])
setup_di(app, container)
container.validate()
```

<!-- invisible-code-block: python
assert app.test_client().get("/report").json == {"service": "catalog"}
-->

Call `container.validate()` after `setup_di`. A factory that takes a `flask.Request` depends on the
context provider that `setup_di` registers, so validating before it fails with
`ValidationFailedError`.

## Injecting into handlers

`FromDI` takes a type, as above, or a provider such as `FromDI(AppGroup.report)`, and resolves it
from the request's child container. A decorated view reached without `setup_di` raises
`RuntimeError`.

### `auto_inject`

Pass `auto_inject=True` to `setup_di` to wrap every registered view, app routes and blueprint
routes alike, without a per-view `@inject`. A view that already carries `@inject` is left alone.

`setup_di` wraps the views registered at the moment you call it, so call it **after** all routes,
blueprint routes included, are registered. A route added later is not wrapped, and a request to it
fails with `TypeError: get_late_report() missing 1 required positional argument: 'report'`:

```python
auto_app = Flask(__name__)


@auto_app.route("/report")
def get_auto_report(report: typing.Annotated[Report, FromDI(Report)]) -> dict[str, str]:
    return report.as_dict()


setup_di(auto_app, Container(groups=[AppGroup]), auto_inject=True)


# Broken: registered after setup_di, so never wrapped
@auto_app.route("/late-report")
def get_late_report(report: typing.Annotated[Report, FromDI(Report)]) -> dict[str, str]:
    return report.as_dict()
```

<!-- invisible-code-block: python
auto_app.testing = True
auto_client = auto_app.test_client()
assert auto_client.get("/report").json == {"service": "catalog"}
try:
    auto_client.get("/late-report")
except TypeError as error:
    assert str(error) == "get_late_report() missing 1 required positional argument: 'report'"
else:
    raise AssertionError("the late route was wrapped")
-->

## Scopes and lifecycle

Flask has no websocket concept, so the integration only ever opens one child scope; see
[the scope hierarchy](../providers/scopes.md#what-each-scope-is-for). `before_request` builds a
`Scope.REQUEST` child of the root container and stores it on `flask.g`, and `teardown_appcontext`
closes it with `close_sync()` once the request, error handling included, is done.

Because the child closes with `close_sync()`, REQUEST-scoped finalizers must be sync. An async
finalizer raises [`AsyncFinalizerInSyncCloseError`](../troubleshooting/async-finalizer-in-sync-close-error.md),
and it or any other failing finalizer reaches Flask as a `FinalizerError` from the teardown. The
request then fails with a 500 under the Werkzeug server, and the test client raises the error.

`setup_di` does not close the root container, because Flask has no application-shutdown hook to
run it from. Close it yourself where your process shuts down, for example with `atexit`. That
close is a `close_sync()` too, so APP-scoped finalizers must be sync as well:

```python
import atexit

from modern_di_flask import fetch_di_container

atexit.register(fetch_di_container(app).close_sync)
```

## Framework context objects

The integration makes `flask.Request` available to your factories. See
[Framework context objects](../providers/context.md#framework-context-objects) for how implicit
and explicit resolution work.

- `flask_request_provider` provides the current `flask.Request` (REQUEST scope). It is registered
  by type.

A factory can receive the request by type, or name the provider in `kwargs`:

```python
from flask import Request
from modern_di_flask import flask_request_provider


def describe_request(request: Request) -> dict[str, str]:
    return {"method": request.method, "url": request.url}


class RequestGroup(Group):
    by_type = providers.Factory(describe_request, scope=Scope.REQUEST, bound_type=None)
    by_provider = providers.Factory(
        describe_request,
        scope=Scope.REQUEST,
        bound_type=None,
        kwargs={"request": flask_request_provider},
    )
```

<!-- invisible-code-block: python
request_app = Flask(__name__)


@request_app.route("/describe")
@inject
def describe(
    by_type: typing.Annotated[dict[str, str], FromDI(RequestGroup.by_type)],
    by_provider: typing.Annotated[dict[str, str], FromDI(RequestGroup.by_provider)],
) -> list[dict[str, str]]:
    return [by_type, by_provider]


setup_di(request_app, Container(groups=[RequestGroup])).validate()
assert request_app.test_client().get("/describe").json == [{"method": "GET", "url": "http://localhost/describe"}] * 2
-->

## See also

- [Testing with overrides](../recipes/testing-overrides.md): swap providers in your tests.
- [Organize a large container with multiple Groups](../recipes/multi-group.md): structuring a larger container.
- [Lifecycle](../providers/lifecycle.md): finalizers and container teardown.
- [Scopes](../providers/scopes.md): the APP → REQUEST lifetime model.

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container, *, auto_inject=False)` | Stores the container on `app.extensions`, registers the request context provider, installs the `before_request`/`teardown_appcontext` pair that builds and closes a per-request `Scope.REQUEST` child container, and, if `auto_inject=True`, wraps every currently registered view with `inject`; returns the container. It does not close the root container. |
| `FromDI(dependency)` | Marker (used with `@inject`) that resolves a provider or type from the per-request child container. |
| `inject` | Decorator for a sync view function; resolves its `FromDI`-annotated parameters. Raises `RuntimeError` naming `setup_di` when a request reaches it without `setup_di` called. |
| `fetch_di_container(app)` | Returns the root `Container` stored on `app.extensions`. |
| `flask_request_provider` | `ContextProvider` for `flask.Request` (REQUEST scope), auto-registered by type. |
