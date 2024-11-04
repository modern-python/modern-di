import typing

import fastapi
import modern_di
from modern_di import Scope, providers
from starlette import status
from starlette.testclient import TestClient

from modern_di_fastapi import Provide, build_request_container
from tests.dependencies import DependentCreator, SimpleCreator, context_adapter_function


app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
request_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)
action_factory = providers.Factory(Scope.ACTION, DependentCreator, dep1=app_factory.cast)
context_adapter = providers.ContextAdapter(Scope.REQUEST, context_adapter_function)


def test_factories(client: TestClient, app: fastapi.FastAPI) -> None:
    @app.get("/")
    async def read_root(
        app_factory_instance: typing.Annotated[SimpleCreator, Provide(app_factory)],
        request_factory_instance: typing.Annotated[DependentCreator, Provide(request_factory)],
    ) -> None:
        assert isinstance(app_factory_instance, SimpleCreator)
        assert isinstance(request_factory_instance, DependentCreator)
        assert request_factory_instance.dep1 is not app_factory_instance

    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() is None


def test_context_adapter(client: TestClient, app: fastapi.FastAPI) -> None:
    @app.get("/")
    async def read_root(
        method: typing.Annotated[str, Provide(context_adapter)],
    ) -> None:
        assert method == "GET"

    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() is None


def test_factories_action_scope(client: TestClient, app: fastapi.FastAPI) -> None:
    @app.get("/")
    async def read_root(
        request_container: typing.Annotated[modern_di.Container, fastapi.Depends(build_request_container)],
    ) -> None:
        with request_container.build_child_container() as action_container:
            action_factory_instance = action_factory.sync_resolve(action_container)
            assert isinstance(action_factory_instance, DependentCreator)

    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() is None
