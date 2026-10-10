<div class="mp-hero" markdown>

<h1 class="mp-lockup">
<img class="mp-logo mp-logo--light" src="assets/lockup-light.svg" alt="modern-di">
<img class="mp-logo mp-logo--dark" src="assets/lockup-dark.svg" alt="" aria-hidden="true">
</h1>

</div>

`modern-di` is a dependency injection container for Python 3.11+. You declare how each object is
built, and the container builds it, fills its constructor from type annotations, keeps it for as
long as its scope lives, and runs its teardown when that scope closes.

- Constructor parameters are matched by type, and you can pass explicit arguments where a type is
  ambiguous.
- Scopes (APP, REQUEST and finer ones) decide how long a cached object lives, and finalizers close
  it when its scope ends.
- `container.validate()` finds cycles and scope errors at startup instead of on the first request.
- One override replaces a dependency for the whole container tree, so HTTP handlers, workers and
  direct unit tests all see the same fake.
- Typed end to end, with no type-checker plugin.
- Integrations for aiogram, aiohttp, arq, Celery, FastAPI, FastMCP, FastStream, Flask, gRPC,
  Litestar, Starlette, taskiq and Typer, plus a pytest plugin.

[About DI](introduction/about-di.md) explains dependency injection from scratch, and
[modern-di vs other libraries](introduction/comparison.md) covers when you need a container and how
modern-di differs from Dishka, dependency-injector and the rest. For complete services, see the [FastAPI](https://github.com/modern-python/fastapi-sqlalchemy-template) and
[Litestar](https://github.com/modern-python/litestar-sqlalchemy-template) templates.

## 1. Install

=== "uv"

    ```bash
    uv add modern-di
    ```

=== "pip"

    ```bash
    pip install modern-di
    ```

=== "poetry"

    ```bash
    poetry add modern-di
    ```

Each framework integration is a separate package named `modern-di-<framework>`, such as
`modern-di-fastapi`. The pytest plugin is `modern-di-pytest`.

## 2. Resolve a dependency

A `Group` lists your providers, and `Container.resolve` builds a value by its type.

```python
import dataclasses

from modern_di import Container, Group, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    api_url: str = "https://api.example.com"


class Dependencies(Group):
    settings = providers.Factory(Settings)


container = Container(groups=[Dependencies])
container.validate()
settings = container.resolve(Settings)
assert settings.api_url == "https://api.example.com"
```

A provider without `scope=` is APP-scoped: it lives as long as the root container. Without `cache=`,
`Factory` calls `Settings` again on every resolve.

## 3. Create once, close at shutdown

`cache=True` keeps the first instance and returns it on every later resolve. To close the instance
when the container closes, pass `CacheSettings` with a `finalizer` instead.

```python
import dataclasses

from modern_di import Container, Group, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    api_url: str = "https://api.example.com"


class HttpClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.api_url
        self.closed = False

    def close(self) -> None:
        self.closed = True


class Dependencies(Group):
    settings = providers.Factory(Settings, cache=True)
    http_client = providers.Factory(HttpClient, cache=providers.CacheSettings(finalizer=HttpClient.close))


with Container(groups=[Dependencies]) as container:
    container.validate()
    client = container.resolve(HttpClient)
    assert container.resolve(HttpClient) is client

assert client.closed
```

`HttpClient` gets its `settings` argument by type, with no wiring code. The `with` block closes the
container on exit, which runs the finalizer. Finalizers may be async; then use `async with`. See
[Lifecycle](providers/lifecycle.md).

## 4. Add a request scope

Some objects should live for one request. Give their provider `scope=Scope.REQUEST`, then resolve
them from a child container built for that request.

```python
import dataclasses

from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    api_url: str = "https://api.example.com"


class HttpClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.api_url
        self.closed = False

    def close(self) -> None:
        self.closed = True


@dataclasses.dataclass(kw_only=True, slots=True)
class UserRepository:
    client: HttpClient

    def find(self, user_id: int) -> dict[str, object]:
        return {"id": user_id, "source": self.client.base_url}


class Dependencies(Group):
    settings = providers.Factory(Settings, cache=True)
    http_client = providers.Factory(HttpClient, cache=providers.CacheSettings(finalizer=HttpClient.close))
    user_repository = providers.Factory(UserRepository, scope=Scope.REQUEST)


with Container(groups=[Dependencies]) as container:
    container.validate()
    with container.build_child_container(scope=Scope.REQUEST) as request_container:
        repository = request_container.resolve(UserRepository)
        assert repository.client is container.resolve(HttpClient)
```

The request container builds `UserRepository` and reaches up to the root for the shared
`HttpClient`. Resolving `UserRepository` from the root container raises `ScopeNotInitializedError`,
because the root has no REQUEST scope; see
[Which container resolves](introduction/resolving.md#which-container-resolves). Values that exist
only at request time, such as the incoming request object, come in through a
[`ContextProvider`](providers/context.md).

## 5. Use it in a framework

An integration builds the request container for each request and closes it afterward. With
FastAPI, install `modern-di-fastapi` and reuse the `Dependencies` group from step 4:

```python
import typing

import fastapi
import modern_di_fastapi
from modern_di import Container


app = fastapi.FastAPI()
container = Container(groups=[Dependencies])
modern_di_fastapi.setup_di(app, container)
container.validate()


@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    repository: typing.Annotated[UserRepository, modern_di_fastapi.FromDI(UserRepository)],
) -> dict[str, object]:
    return repository.find(user_id)
```

`setup_di` also closes the root container at shutdown, which runs the `HttpClient` finalizer. The
other integrations work the same way; each has its own page under Integrations, starting with
[FastAPI](integrations/fastapi.md).

## 6. Override in tests

`container.override` replaces a provider for the whole container tree. Used as a context manager,
it restores the original on exit.

```python
fake_client = HttpClient(settings=Settings(api_url="http://test"))

with Container(groups=[Dependencies]) as container:
    with container.override(Dependencies.http_client, fake_client):
        with container.build_child_container(scope=Scope.REQUEST) as request_container:
            assert request_container.resolve(UserRepository).client is fake_client
```

The override reaches every request container, including the ones an integration builds, so the
FastAPI route above would see the fake too. See [Testing with overrides](recipes/testing-overrides.md).

## Where to next

- [Resolving](introduction/resolving.md): how parameters are matched by type, and what happens when
  they can't be.
- [Scopes](providers/scopes.md): the full scope model, from APP down to STEP.
- [Factories](providers/factories.md): every `Factory` option.
- [Lifecycle](providers/lifecycle.md): finalizers, async teardown and validation.
- [Recipes](recipes/sqlalchemy.md): async SQLAlchemy, lifespan-managed resources and more.
- [Good and bad practices](recipes/good-and-bad-practices.md): common mistakes and how modern-di
  catches each one.
