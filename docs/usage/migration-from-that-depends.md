# Migration from `that-depends`

## 1. Adapt dependencies graph
1. Use `modern-di.BaseGraph` instead of `that-depends.BaseContainer`.
2. Add scopes to all providers.
   - Most of the providers will be `APP` scope.
   - ContextResource usually becomes `Resource` of `REQUEST`-scope.


`that-depends`:
```python
from that_depends import BaseContainer, providers

from app import repositories
from app.resources.db import create_sa_engine, create_session


class IOCContainer(BaseContainer):
    database_engine = providers.Resource(create_sa_engine, settings=settings.cast)
    session = providers.ContextResource(create_session, engine=database_engine.cast)
    decks_service = providers.Factory(repositories.DecksService, session=session)
    cards_service = providers.Factory(repositories.CardsService, session=session)
```

`modern-di`:
```python
from modern_di import BaseGraph, Scope, providers

from app import repositories
from app.resources.db import create_sa_engine, create_session


class Dependencies(BaseGraph):
    database_engine = providers.Resource(Scope.APP, create_sa_engine)
    session = providers.Resource(Scope.REQUEST, create_session, engine=database_engine.cast)

    decks_service = providers.Factory(Scope.REQUEST, repositories.DecksService, session=session.cast)
    cards_service = providers.Factory(Scope.REQUEST, repositories.CardsService, session=session.cast)
```

## 2. Adapt integration with framework

For fastapi it will be something like this:

```python
import contextlib
import typing

import fastapi
import modern_di_fastapi

from app.ioc import Dependencies


@contextlib.asynccontextmanager
async def lifespan_manager(app: fastapi.FastAPI) -> typing.AsyncIterator[dict[str, typing.Any]]:
   async with modern_di_fastapi.fetch_di_container(app) as di_container:
      await Dependencies.async_resolve_creators(di_container)
      yield {}


app = fastapi.FastAPI(lifespan=lifespan_manager)
modern_di_fastapi.setup_di(app)
```