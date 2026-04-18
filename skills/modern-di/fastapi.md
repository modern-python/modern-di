# modern-di — FastAPI Integration

Install: `pip install modern-di-fastapi`

## Setup

```python
import fastapi
import modern_di
import modern_di_fastapi

from app import ioc

def build_app() -> fastapi.FastAPI:
    app = fastapi.FastAPI()
    di_container = modern_di.Container(groups=[ioc.Dependencies])
    modern_di_fastapi.setup_di(app, di_container)
    return app
```

`setup_di` handles everything:
- Stores the container in `app.state`
- Registers `fastapi.Request` as a `ContextProvider` at `Scope.REQUEST`
- Registers `fastapi.WebSocket` as a `ContextProvider` at `Scope.SESSION`
- Wraps the app lifespan to call `container.close_async()` on shutdown

## Route handlers

Unlike Litestar, FastAPI uses `FromDI` **inline** in the handler signature as a default value:

```python
import typing
import fastapi
from modern_di_fastapi import FromDI

from app import schemas
from app.repositories import DecksRepository

ROUTER = fastapi.APIRouter(prefix="/api")

@ROUTER.get("/decks/")
async def list_decks(
    decks_repository: DecksRepository = FromDI(DecksRepository),
) -> schemas.Decks:
    objects = await decks_repository.list()
    return {"items": objects}

@ROUTER.get("/decks/{deck_id}/")
async def get_deck(
    deck_id: int,
    decks_repository: DecksRepository = FromDI(DecksRepository),
) -> schemas.Deck:
    instance = await decks_repository.get_one_or_none(...)
    if not instance:
        raise fastapi.HTTPException(status_code=404)
    return schemas.Deck.model_validate(instance)

@ROUTER.post("/decks/")
async def create_deck(
    data: schemas.DeckCreate,
    decks_repository: DecksRepository = FromDI(DecksRepository),
) -> schemas.Deck:
    instance = await decks_repository.create(data)
    return schemas.Deck.model_validate(instance)
```

You can also use `Annotated` style:
```python
async def list_decks(
    decks_repository: typing.Annotated[DecksRepository, FromDI(DecksRepository)],
) -> schemas.Decks:
    ...
```

## FromDI

```python
modern_di_fastapi.FromDI(dependency, *, use_cache=True)
```

Accepts either:
- A **type** — resolved by looking it up in the providers registry
- A **provider reference** — resolved directly (`Dependencies.decks_repository`)

Returns a `fastapi.Depends(...)` cast to the correct type. FastAPI handles calling it and injecting
the result.

## Key difference from Litestar

| | Litestar | FastAPI |
|---|---|---|
| Setup | `ModernDIPlugin(container)` in plugins | `setup_di(app, container)` call |
| Wiring dependencies | Centrally in `AppConfig.dependencies` | `FromDI(Type)` inline in each handler |
| Handler parameters | Plain type annotations — no markers | `= FromDI(...)` or `Annotated[T, FromDI(...)]` |

## Accessing the Request inside a provider

`setup_di` registers `fastapi.Request` automatically. Any creator that type-annotates a
`fastapi.Request` parameter gets it auto-injected:

```python
def fetch_method(request: fastapi.Request) -> str:
    return request.method

class Dependencies(Group):
    request_method = providers.Factory(
        scope=Scope.REQUEST,
        creator=fetch_method,
        bound_type=None,  # prevent registering str as a provider
    )

@app.get("/")
async def endpoint(
    method: str = FromDI(Dependencies.request_method),
) -> dict:
    return {"method": method}
```

## WebSocket scoping

WebSocket connections use `Scope.SESSION`. `setup_di` registers `fastapi.WebSocket` as a
`ContextProvider` at `Scope.SESSION` automatically.

## ACTION scope (advanced)

Inject the request container directly to build deeper scope chains:

```python
from modern_di import Container
from modern_di_fastapi import build_di_container

@app.get("/")
async def endpoint(
    request_container: typing.Annotated[Container, fastapi.Depends(build_di_container)],
) -> dict:
    action_container = request_container.build_child_container(scope=Scope.ACTION)
    result = action_container.resolve_provider(Dependencies.action_factory)
    await action_container.close_async()
    return {"result": result}
```

## Full example (from fastapi-sqlalchemy-template)

```
app/
├── ioc.py           — Dependencies(Group) with engine, session, repositories
├── resources/
│   └── db.py        — create_sa_engine, close_sa_engine, create_session, close_session
├── repositories.py  — DecksRepository, CardsRepository
├── api/
│   └── decks.py     — route handlers with FromDI() inline
└── application.py   — build_app() with setup_di(app, container)
```

See `common.md` for the `ioc.py` and `db.py` content.
