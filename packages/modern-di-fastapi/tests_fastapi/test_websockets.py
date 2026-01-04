import typing

import fastapi
from modern_di import Container
from modern_di_fastapi import FromDI, build_di_container
from starlette.testclient import TestClient

from tests_fastapi.dependencies import Dependencies, DependentCreator, SimpleCreator


async def test_factories(client: TestClient, app: fastapi.FastAPI) -> None:
    @app.websocket("/ws")
    async def websocket_endpoint(
        websocket: fastapi.WebSocket,
        app_factory_instance: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
        session_factory_instance: typing.Annotated[DependentCreator, FromDI(Dependencies.session_factory)],
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
        session_container: typing.Annotated[Container, fastapi.Depends(build_di_container)],
    ) -> None:
        request_container = session_container.build_child_container()
        request_factory_instance = request_container.resolve_provider(Dependencies.request_factory)
        assert isinstance(request_factory_instance, DependentCreator)

        await websocket.accept()
        await websocket.send_text("test")
        await websocket.close()

    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_text()
        assert data == "test"


async def test_context_provider(client: TestClient, app: fastapi.FastAPI) -> None:
    @app.websocket("/ws")
    async def websocket_endpoint(
        websocket: fastapi.WebSocket,
        path: typing.Annotated[str, FromDI(Dependencies.websocket_path)],
    ) -> None:
        assert path == "/ws"

        await websocket.accept()
        await websocket.send_text("test")
        await websocket.close()

    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_text()
        assert data == "test"
