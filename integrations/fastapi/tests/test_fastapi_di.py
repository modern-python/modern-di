import contextlib
import dataclasses
import typing

import fastapi
import httpx
import modern_di
import pytest
from asgi_lifespan import LifespanManager
from modern_di import Scope, providers
from starlette import status
from starlette.requests import Request

from modern_di_fastapi import FromDI, save_di_container
from modern_di_fastapi.main import enter_di_request_scope


@contextlib.asynccontextmanager
async def lifespan(app_: fastapi.FastAPI) -> typing.AsyncIterator[None]:
    di_container = modern_di.Container(scope=modern_di.Scope.APP)
    save_di_container(app_, di_container)
    async with di_container:
        yield


app = fastapi.FastAPI(lifespan=lifespan, dependencies=[fastapi.Depends(enter_di_request_scope)])


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
        yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_read_main(client: httpx.AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == "GET"
