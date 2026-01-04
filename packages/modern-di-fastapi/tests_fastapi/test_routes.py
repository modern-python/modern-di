import typing

import fastapi
from modern_di import Container
from modern_di_fastapi import FromDI, build_di_container
from starlette import status
from starlette.testclient import TestClient

from tests_fastapi.dependencies import Dependencies, DependentCreator, SimpleCreator


def test_factories(client: TestClient, app: fastapi.FastAPI) -> None:
    @app.get("/")
    async def read_root(
        app_factory_instance: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
        request_factory_instance: typing.Annotated[DependentCreator, FromDI(Dependencies.request_factory)],
    ) -> None:
        assert isinstance(app_factory_instance, SimpleCreator)
        assert isinstance(request_factory_instance, DependentCreator)
        assert request_factory_instance.dep1 is not app_factory_instance

    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() is None


def test_context_provider(client: TestClient, app: fastapi.FastAPI) -> None:
    @app.get("/")
    async def read_root(
        method: typing.Annotated[str, FromDI(Dependencies.request_method)],
    ) -> None:
        assert method == "GET"

    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() is None


def test_factories_action_scope(client: TestClient, app: fastapi.FastAPI) -> None:
    @app.get("/")
    async def read_root(
        request_container: typing.Annotated[Container, fastapi.Depends(build_di_container)],
    ) -> None:
        action_container = request_container.build_child_container()
        action_factory_instance = action_container.resolve_provider(Dependencies.action_factory)
        assert isinstance(action_factory_instance, DependentCreator)

    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() is None
