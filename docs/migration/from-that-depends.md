# Migration from `that-depends`

## 1. Install `modern-di` using your favorite tool:

If you need only `modern-di` without integrations:

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

If you need to integrate with some framework, then install `modern-di-*`.

## 2. Migrate dependencies graph
1. Use `modern-di.Group` instead of `that-depends.BaseContainer`.
2. Add scopes to providers.
   - Most of the providers will be `APP` scope which is the default value.
   - SQLAlchemy orm session becomes Factory of `REQUEST`-scope with cache_settings and finalizer to close connections.
   - Repositories depending on ORM-session becomes factories of `REQUEST`-scope.

=== "that-depends"

      ```python
      from that_depends import BaseContainer, providers

      from app import repositories
      from app.resources.db import create_sa_engine, create_session


      class Dependencies(BaseContainer):
          database_engine = providers.Resource(create_sa_engine, settings=settings.cast)
          session = providers.ContextResource(create_session, engine=database_engine.cast)

          decks_service = providers.Factory(repositories.DecksService, session=session)
          cards_service = providers.Factory(repositories.CardsService, session=session)
      ```

=== "modern-di"

      ```python
      from modern_di import Group, Scope, providers

      from app.repositories import CardsRepository, DecksRepository
      from app.resources.db import close_sa_engine, close_session, create_sa_engine, create_session


      class Dependencies(Group):
          database_engine = providers.Factory(
              creator=create_sa_engine, cache_settings=providers.CacheSettings(finalizer=close_sa_engine)
          )
          session = providers.Factory(
              scope=Scope.REQUEST, creator=create_session, cache_settings=providers.CacheSettings(finalizer=close_session)
          )

          decks_repository = providers.Factory(
              scope=Scope.REQUEST,
              creator=DecksRepository,
              kwargs={"auto_commit": True, "session": session},
          )
          cards_repository = providers.Factory(
              scope=Scope.REQUEST,
              creator=CardsRepository,
              kwargs={"auto_commit": True, "session": session},
          )

      ```

## 3. Migrate integration with framework

Usage examples:

- with LiteStar - [litestar-sqlalchemy-template](https://github.com/modern-python/litestar-sqlalchemy-template)
- with FastAPI - [fastapi-sqlalchemy-template](https://github.com/modern-python/fastapi-sqlalchemy-template)

=== "fastapi"

      ```python
      import fastapi
      from modern_di import Container
      import modern_di_fastapi

      from app.ioc import Dependencies


      container = Container(groups=[Dependencies])

      app = fastapi.FastAPI()
      modern_di_fastapi.setup_di(app, container)
      ```

=== "litestar"

      ```python
      from litestar import Litestar
      from modern_di import Container
      import modern_di_litestar

      from app.ioc import Dependencies


      container = Container(groups=[Dependencies])

      app = Litestar(
          route_handlers=[...],
          plugins=[modern_di_litestar.ModernDIPlugin(container)],
      )
      ```

## 4. Migrate routes

=== "fastapi"

      For `fastapi` replace `fastapi.Depends` with `modern_di_fastapi.FromDI`:

      ```python
      import fastapi
      from modern_di_fastapi import FromDI

      from app import ioc, schemas
      from app.repositories import DecksService


      ROUTER: typing.Final = fastapi.APIRouter()


      @ROUTER.get("/decks/")
      async def list_decks(
           decks_service: DecksService = FromDI(DecksService),
      ) -> schemas.Decks:
         objects = await decks_service.list()
         return schemas.Decks(items=objects)
      ```

=== "litestar"

      For `litestar` replace `litestar.di.Provide` with `modern_di_litestar.FromDI`

      ```python
      import litestar
      from modern_di_litestar import FromDI

      from app import ioc, schemas
      from app.repositories import DecksService


      @litestar.get("/decks/", dependencies={
         "decks_service": FromDI(DecksService),
      })
      async def list_decks(decks_service: DecksService) -> schemas.Decks:
         objects = await decks_service.list()
         return schemas.Decks(items=objects)
      ```

## 5. More info about providers replacements:

- `Singleton` becomes `Factory` of `APP`-scope with cache_settings
```python
# that-depends
some_singleton = providers.Singleton(SomeClass)

# modern-di
some_factory = providers.Factory(
  creator=SomeClass,
  cache_settings=providers.CacheSettings()
)
```

- `Resource` becomes `Factory` of `APP`-scope with cache_settings and finalizer
```python
# that-depends
some_resource = providers.Resource(create_resource)  # async or sync generator

# modern-di
some_factory = providers.Factory(
  scope=Scope.APP,
  creator=create_resource,  # sync function
  cache_settings=providers.CacheSettings(finalizer=close_resource),  # async or sync function
)
```

- `List` and `Dict` becomes `Factory` which accepts some dependencies and returns list or dict accordingly
```python
# that-depends
some_list = providers.List(provider1, provider2)

# modern-di
def build_list(dep1: SomeType1, dep2: SomeType2) -> list:
    return [dep1, dep2]

some_factory = providers.Factory(creator=build_list)
```

- `ContextResource` usually similar to `Resource` becomes `Factory` with `cache_settings` and `finalizer`. The difference is in scope which is usually `REQUEST`.

- `Factory` stays `Factory` without `cache_settings`
