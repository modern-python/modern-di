<div class="mp-hero" markdown>

<h1 class="mp-lockup">
<img class="mp-logo mp-logo--light" src="assets/lockup-light.svg" alt="modern-di">
<img class="mp-logo mp-logo--dark" src="assets/lockup-dark.svg" alt="" aria-hidden="true">
</h1>

</div>

`modern-di` is a Python dependency injection framework which supports the following:

- Automatic dependency graph based on type annotations
- Also, explicit dependencies are allowed where needed
- Scopes and context management
- Python 3.10+ support
- Fully typed and tested
- Integrations with `aiohttp`, `FastAPI`, `FastStream`, `Litestar`, `Starlette`, `Typer`, and `pytest`

Reference templates:

- Litestar — [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)
- FastAPI — [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template)

For end-to-end patterns drawn from real services, see the [Recipes](recipes/sqlalchemy.md) section.

---

# Quickstart

## 1. Install `modern-di`

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

If you want a framework integration, install the matching adapter — e.g. `modern-di-aiohttp`, `modern-di-fastapi`, `modern-di-litestar`, `modern-di-faststream`, `modern-di-starlette`, `modern-di-typer`. For pytest support, install `modern-di-pytest`.

## 2. Describe your dependencies

Two providers, two scopes: a `Settings` shared by the whole process, and a `UserRepository` rebuilt per request.

```python
import dataclasses


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    database_url: str = "postgresql+asyncpg://localhost/app"


@dataclasses.dataclass(kw_only=True, slots=True)
class UserRepository:
    settings: Settings    # auto-injected by type

    def find(self, user_id: int) -> dict[str, int]:
        return {"id": user_id}
```

## 3. Declare a Group

A `Group` is a namespace that lists your providers. You instantiate a `Container` from it; the `Group` itself is schema only.

```python
from modern_di import Group, Scope, providers


class Dependencies(Group):
    settings = providers.Factory(
        scope=Scope.APP,                          # APP is the default
        creator=Settings,
        cache=True,  # cache the singleton for the whole app
    )

    user_repository = providers.Factory(
        scope=Scope.REQUEST,                       # rebuilt for each request
        creator=UserRepository,
    )
```

## 4. Wire it up

Pick **one** of the two mutually-exclusive options below.

### Option A — integrate with your framework

Pick the integration you need:

- [aiohttp](integrations/aiohttp.md)
- [FastAPI](integrations/fastapi.md)
- [FastStream](integrations/faststream.md)
- [Litestar](integrations/litestar.md)
- [Starlette](integrations/starlette.md)
- [Typer](integrations/typer.md)
- [Pytest](integrations/pytest.md)

The integration package builds the per-request child container automatically and closes the APP container at shutdown.

### Option B — use modern-di directly

```python
from modern_di import Container, Scope


# Pass validate=True to detect cycles and scope-chain errors at startup
with Container(groups=[Dependencies], validate=True) as container:
    # APP-scoped providers resolve straight from the container
    settings = container.resolve(Settings)

    # REQUEST-scoped providers need a REQUEST child container
    with container.build_child_container(scope=Scope.REQUEST) as request:
        repo = request.resolve(UserRepository)
        user = repo.find(42)

    # Request-scope finalizers (teardown hooks such as closing a DB connection) ran on `with` exit
# App-scope finalizers ran on the outer `with` exit
```

Resolution is always synchronous. Use `async with` (on both the container and the child) only when a
provider registers an **async** finalizer — see [Lifecycle](providers/lifecycle.md).

## Where to next

- [Resolving](introduction/resolving.md) — how type-based auto-injection works.
- [Factories](providers/factories.md) — the provider you just used.
- [Scopes](providers/scopes.md) — the APP → REQUEST lifetime model in one page.
- [Lifecycle](providers/lifecycle.md) — finalizers, `close_async()`, validation.
- [Recipes](recipes/sqlalchemy.md) — async SQLAlchemy, lifespan-managed resources, testing with overrides.
