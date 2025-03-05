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
1. Use `modern-di.BaseGraph` instead of `that-depends.BaseContainer`.
2. Add scopes to all providers.
   - Most of the providers will be `APP` scope.
   - ContextResource usually becomes `Resource` of `REQUEST`-scope.
   - Dependents of ContextResource usually has `REQUEST`-scope as well.

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
      from modern_di import BaseGraph, Scope, providers
      
      from app import repositories
      from app.resources.db import create_sa_engine, create_session
      
      
      class Dependencies(BaseGraph):
          database_engine = providers.Resource(Scope.APP, create_sa_engine)
          session = providers.Resource(Scope.REQUEST, create_session, engine=database_engine.cast)
      
          decks_service = providers.Factory(Scope.REQUEST, repositories.DecksService, session=session.cast)
          cards_service = providers.Factory(Scope.REQUEST, repositories.CardsService, session=session.cast)
      ```

## 3. Migrate integration with framework

=== "fastapi"

      ```python
      import contextlib
      import typing
      
      import fastapi
      import modern_di_fastapi
      
      from app.ioc import Dependencies
      
      
      @contextlib.asynccontextmanager
      async def lifespan_manager(app_: fastapi.FastAPI) -> typing.AsyncIterator[dict[str, typing.Any]]:
         async with modern_di_fastapi.fetch_di_container(app_) as di_container:
            await Dependencies.async_resolve_creators(di_container)
            yield {}
      
      
      app = fastapi.FastAPI(lifespan=lifespan_manager)
      modern_di_fastapi.setup_di(app)
      ```

=== "litestar"

      ```python
      import contextlib
      import typing
      
      from litestar import Litestar
      import modern_di_litestar
      
      
      @contextlib.asynccontextmanager
      async def lifespan_manager(app_: Litestar) -> typing.AsyncIterator[None]:
          async with modern_di_litestar.fetch_di_container(app_):
              yield
      
      
      app = Litestar(
          route_handlers=[...],
          dependencies={**modern_di_litestar.prepare_di_dependencies()},
          lifespan=[lifespan_manager],
      )
      modern_di_litestar.setup_di(app)
      ```

## 4. Migrate routes

=== "fastapi"

      For `fastapi` replace `fastapi.Depends` with `modern_di_fastapi.FromDI`:
      
      ```python
      import typing
      
      import fastapi
      from modern_di_fastapi import FromDI
      
      from app import ioc, schemas
      from app.repositories import DecksService
      
      
      ROUTER: typing.Final = fastapi.APIRouter()
      
      
      @ROUTER.get("/decks/")
      async def list_decks(
           decks_service: DecksService = FromDI(ioc.Dependencies.decks_service),
      ) -> schemas.Decks:
         objects = await decks_service.list()
         return typing.cast(schemas.Decks, {"items": objects})
      ```

=== "litestar"

      For `litestar` replace `litestar.di.Provide` with `modern_di_litestar.FromDI`
      
      ```python
      import litestar
      import modern_di_litestar
      
      from app import ioc, schemas
      from app.repositories import DecksService
      
      
      @litestar.get("/decks/", dependencies={
         "decks_service": modern_di_litestar.FromDI(ioc.Dependencies.decks_service),
      })
      async def list_decks(decks_service: DecksService) -> schemas.Decks:
         objects = await decks_service.list()
         return schemas.Decks(items=objects)
      ```
