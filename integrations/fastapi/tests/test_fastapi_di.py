import contextlib
import dataclasses
import typing

import fastapi
import httpx
import modern_di
import pytest
from asgi_lifespan import LifespanManager
from modern_di import Scope, resolvers
from starlette import status

import modern_di_fastapi
from modern_di_fastapi import FromDI


@contextlib.asynccontextmanager
async def lifespan(app_: fastapi.FastAPI) -> typing.AsyncIterator[None]:
    di_container = modern_di.Container(scope=modern_di.Scope.APP)
    modern_di_fastapi.setup_modern_di(container=di_container, app=app_)
    async with di_container:
        yield


app = fastapi.FastAPI(lifespan=lifespan)
app.add_middleware(modern_di_fastapi.ContainerMiddleware)


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


app_factory = resolvers.Factory(Scope.APP, SimpleCreator, dep1="original")
request_factory = resolvers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)


@app.get("/")
async def read_root(
    app_factory_instance: typing.Annotated[SimpleCreator, FromDI(app_factory)],
    request_factory_instance: typing.Annotated[DependentCreator, FromDI(request_factory)],
) -> str:
    assert isinstance(app_factory_instance, SimpleCreator)
    assert isinstance(request_factory_instance, DependentCreator)
    return app_factory_instance.dep1


@pytest.fixture(scope="session")
async def client() -> typing.AsyncIterator[httpx.AsyncClient]:
    async with LifespanManager(app):
        yield httpx.AsyncClient(app=app, base_url="http://test")


async def test_read_main(client: httpx.AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == status.HTTP_200_OK
