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

## 2. First success

One provider, no scopes, no caching — the smallest honest example. A `Group` is a namespace that
lists your providers; `Factory` defaults to `scope=Scope.APP`; `Container.resolve` looks a value up
by its type.

```python
import dataclasses

from modern_di import Container, Group, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    database_url: str = "postgresql+asyncpg://localhost/app"


class Dependencies(Group):
    settings = providers.Factory(creator=Settings)


# Pass validate=True to detect cycles and scope-chain errors at startup
container = Container(groups=[Dependencies], validate=True)
settings = container.resolve(Settings)
print(settings.database_url)
```

Without `cache=`, `Factory` calls the creator on every resolve — fine for cheap, stateless objects,
but not what you want for a database engine you only want to build once.

## 3. Create once, reuse

Add `cache=True` (via `CacheSettings`, which also lets you attach a finalizer) to turn `settings`
into a singleton, and switch to the `with` form so the finalizer runs when the container closes.

```python
import dataclasses

from modern_di import Container, Group, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    database_url: str = "postgresql+asyncpg://localhost/app"


def close_settings(settings: Settings) -> None:
    print(f"closing settings ({id(settings)})")


class Dependencies(Group):
    settings = providers.Factory(
        creator=Settings,
        cache=providers.CacheSettings(finalizer=close_settings),
    )


with Container(groups=[Dependencies], validate=True) as container:
    first = container.resolve(Settings)
    second = container.resolve(Settings)
    assert first is second  # same instance, cached on first resolve
# `close_settings` ran here, on `with` exit
```

## 4. Request scope

Real apps also need state that lives for one request: a `UserRepository` rebuilt per request, fed
by a `RequestId` supplied at request time via `ContextProvider`. Build a `Scope.REQUEST` child
container with `build_child_container(scope=..., context={...})`; it can still resolve the
APP-scoped `Settings` through the parent.

```python
import dataclasses

from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class Settings:
    database_url: str = "postgresql+asyncpg://localhost/app"


def close_settings(settings: Settings) -> None:
    print(f"closing settings ({id(settings)})")


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class RequestId:
    value: str


@dataclasses.dataclass(kw_only=True, slots=True)
class UserRepository:
    settings: Settings       # auto-injected by type, resolved through the request container
    request_id: RequestId    # supplied via context, one value per request

    def find(self, user_id: int) -> dict[str, object]:
        return {"id": user_id, "request_id": self.request_id.value}


class Dependencies(Group):
    settings = providers.Factory(
        creator=Settings,
        cache=providers.CacheSettings(finalizer=close_settings),
    )
    request_id = providers.ContextProvider(scope=Scope.REQUEST, context_type=RequestId)
    user_repository = providers.Factory(scope=Scope.REQUEST, creator=UserRepository)


with Container(groups=[Dependencies], validate=True) as container:
    request_context = {RequestId: RequestId(value="req-1")}
    with container.build_child_container(scope=Scope.REQUEST, context=request_context) as request:
        repo = request.resolve(UserRepository)
        user = repo.find(42)
    # REQUEST-scope finalizers ran here (none declared in this example)
# APP-scope finalizers ran here (closes settings)
```

A framework integration (linked under "Where to next" below) builds and tears down this REQUEST
child container for you automatically. Resolution itself is always synchronous; use `async with`
instead of `with` only when a provider registers an **async** finalizer — see
[Lifecycle](providers/lifecycle.md).

## Where to next

- Framework integrations — [aiohttp](integrations/aiohttp.md), [FastAPI](integrations/fastapi.md),
  [FastStream](integrations/faststream.md), [Litestar](integrations/litestar.md),
  [Starlette](integrations/starlette.md), [Typer](integrations/typer.md),
  [Pytest](integrations/pytest.md) — each builds the per-request child container automatically and
  closes the APP container at shutdown.
- [Resolving](introduction/resolving.md) — how type-based auto-injection works.
- [Factories](providers/factories.md) — the provider you just used.
- [Scopes](providers/scopes.md) — the APP → REQUEST lifetime model in one page.
- [Lifecycle](providers/lifecycle.md) — finalizers, `close_async()`, validation.
- [Recipes](recipes/sqlalchemy.md) — async SQLAlchemy, lifespan-managed resources, testing with overrides.
- [Good and bad practices](recipes/good-and-bad-practices.md) — named footguns and the mechanism that catches each one.
