import typing

import fastapi
import modern_di
from modern_di import Scope, providers
from modern_di_fastapi import FromDI, build_di_container
from starlette.testclient import TestClient

from tests_fastapi.dependencies import DependentCreator, SimpleCreator


def context_adapter_function(*, websocket: fastapi.WebSocket, **_: object) -> str:
    return str(websocket.scope["path"])


app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
session_factory = providers.Factory(Scope.SESSION, DependentCreator, dep1=app_factory.cast)
request_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)
context_adapter = providers.ContextAdapter(Scope.SESSION, context_adapter_function)


async def test_factories(client: TestClient, app: fastapi.FastAPI) -> None:
    @app.websocket("/ws")
    async def websocket_endpoint(
        websocket: fastapi.WebSocket,
        app_factory_instance: typing.Annotated[SimpleCreator, FromDI(app_factory)],
        session_factory_instance: typing.Annotated[DependentCreator, FromDI(session_factory)],
    ) -> None:
        assert isinstance(app_factory_instance, SimpleCreator)
        assert isinstance(session_factory_instance, DependentCreator)
        assert session_factory_instance.dep1 is not app_factory_instance

        await websocket.accept()
        await websocket.send_text("test")
        await websocket.close()

    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_text()
        assert data == "test"


async def test_factories_request_scope(client: TestClient, app: fastapi.FastAPI) -> None:
    @app.websocket("/ws")
    async def websocket_endpoint(
        websocket: fastapi.WebSocket,
        session_container: typing.Annotated[modern_di.Container, fastapi.Depends(build_di_container)],
    ) -> None:
        with session_container.build_child_container() as request_container:
            request_factory_instance = request_factory.sync_resolve(request_container)
            assert isinstance(request_factory_instance, DependentCreator)

        await websocket.accept()
        await websocket.send_text("test")
        await websocket.close()

    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_text()
        assert data == "test"


async def test_context_adapter(client: TestClient, app: fastapi.FastAPI) -> None:
    @app.websocket("/ws")
    async def websocket_endpoint(
        websocket: fastapi.WebSocket,
        path: typing.Annotated[str, FromDI(context_adapter)],
    ) -> None:
        assert path == "/ws"

        await websocket.accept()
        await websocket.send_text("test")
        await websocket.close()

    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_text()
        assert data == "test"
