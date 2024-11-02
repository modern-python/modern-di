import contextlib
import dataclasses
import typing

import fastapi
import httpx
import modern_di
import modern_di_fastapi
import pytest
from asgi_lifespan import LifespanManager
from modern_di import Scope, providers
from modern_di_fastapi import ContainerMiddleware, FromDI
from starlette import status
from starlette.requests import Request


@contextlib.asynccontextmanager
async def lifespan(app_: fastapi.FastAPI) -> typing.AsyncIterator[None]:
    di_container = modern_di.Container(scope=modern_di.Scope.APP)
    modern_di_fastapi.setup_modern_di(container=di_container, app=app_)
    async with di_container:
        yield


app = fastapi.FastAPI(lifespan=lifespan)
app.add_middleware(ContainerMiddleware)


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


def context_adapter_function(*, request: Request, **_: object) -> str:
    return request.method


app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
request_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)
context_adapter = providers.ContextAdapter(Scope.REQUEST, context_adapter_function)


@app.get("/")
async def read_root(
    app_factory_instance: typing.Annotated[SimpleCreator, FromDI(app_factory)],
    request_factory_instance: typing.Annotated[DependentCreator, FromDI(request_factory)],
    method: typing.Annotated[str, FromDI(context_adapter)],
) -> str:
    assert isinstance(app_factory_instance, SimpleCreator)
    assert isinstance(request_factory_instance, DependentCreator)
    return method


@pytest.fixture(scope="session")
async def client() -> typing.AsyncIterator[httpx.AsyncClient]:
    async with LifespanManager(app):
        yield httpx.AsyncClient(app=app, base_url="http://test")


async def test_read_main(client: httpx.AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == "GET"
