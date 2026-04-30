# modern-di — Litestar Integration

Install: `pip install modern-di-litestar`

## Setup

### Option A — manual `FromDI` wiring

```python
import modern_di
import modern_di_litestar
from litestar import Litestar

from app import ioc, repositories

def build_app() -> Litestar:
    di_container = modern_di.Container(groups=[ioc.Dependencies])
    return Litestar(
        plugins=[modern_di_litestar.ModernDIPlugin(di_container)],
        dependencies={
            "decks_repository": modern_di_litestar.FromDI(repositories.DecksRepository),
            "cards_repository": modern_di_litestar.FromDI(repositories.CardsRepository),
        },
        route_handlers=[ROUTER],
    )
```

### Option B — `autowired_groups` (auto-wiring)

Pass `autowired_groups` to register every provider in those groups as a Litestar dependency, keyed by
its attribute name. No per-route `FromDI` needed:

```python
import modern_di
import modern_di_litestar
from litestar import Litestar

from app import ioc

GROUPS = [ioc.Dependencies]

def build_app() -> Litestar:
    di_container = modern_di.Container(groups=GROUPS)
    return Litestar(
        plugins=[modern_di_litestar.ModernDIPlugin(di_container, autowired_groups=GROUPS)],
        route_handlers=[ROUTER],
    )
```

Route handlers can then declare providers by attribute name directly as parameters.
If the same name appears in multiple groups, a `UserWarning` is emitted and the later group wins.

---

`ModernDIPlugin` handles:
- Registers `litestar.Request` and `litestar.WebSocket` as `ContextProvider`s (REQUEST and SESSION scope)
- Creates a per-request child container and closes it (calling finalizers) after each response
- Stores the container in `app.state.di_container`

## Route handlers

```python
import litestar
from app import models, schemas
from app.repositories import DecksRepository

@litestar.get("/decks/")
async def list_decks(decks_repository: DecksRepository) -> schemas.Decks:
    objects = await decks_repository.list()
    return schemas.Decks(items=objects)

@litestar.get("/decks/{deck_id:int}/")
async def get_deck(deck_id: int, decks_repository: DecksRepository) -> schemas.Deck:
    instance = await decks_repository.get_one_or_none(models.Deck.id == deck_id)
    if not instance:
        raise litestar.exceptions.HTTPException(status_code=404)
    return schemas.Deck.model_validate(instance)

@litestar.post("/decks/")
async def create_deck(data: schemas.DeckCreate, decks_repository: DecksRepository) -> schemas.Deck:
    instance = await decks_repository.create(data)
    return schemas.Deck.model_validate(instance)
```

## FromDI

```python
modern_di_litestar.FromDI(dependency)
```

Accepts either:
- A **type** — resolved by looking it up in the providers registry
- A **provider reference** — resolved directly (`Dependencies.users_repo`)

Returns a Litestar `Provide` object with `use_cache=False` (always fresh per request).

## Accessing the Request inside a provider

`ModernDIPlugin` automatically registers `litestar.Request` as a context provider at `Scope.REQUEST`.
Any creator that type-annotates a `litestar.Request` parameter gets it auto-injected:

```python
def build_audit_logger(request: litestar.Request) -> AuditLogger:
    return AuditLogger(user_id=request.user.id)

class Dependencies(Group):
    audit_logger = providers.Factory(scope=Scope.REQUEST, creator=build_audit_logger)
```

## WebSocket scoping

WebSocket connections use `Scope.SESSION` (not `Scope.REQUEST`). `ModernDIPlugin` registers
`litestar.WebSocket` as a `ContextProvider` at `Scope.SESSION` automatically.

## Full example (from litestar-sqlalchemy-template)

```
app/
├── ioc.py           — Dependencies(Group) with engine, session, repositories
├── resources/
│   └── db.py        — create_sa_engine, close_sa_engine, create_session, close_session
├── repositories.py  — DecksRepository, CardsRepository
├── api/
│   └── decks.py     — route handlers (plain parameters, no DI markers)
└── application.py   — build_app() with ModernDIPlugin + FromDI in dependencies dict
```

See `common.md` for the `ioc.py` and `db.py` content.
