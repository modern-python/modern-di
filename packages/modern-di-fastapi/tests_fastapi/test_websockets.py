import typing

import fastapi
from modern_di import AsyncContainer, Scope, providers
from modern_di_fastapi import FromDI, build_di_container
from starlette.testclient import TestClient

from tests_fastapi.dependencies import DependentCreator, SimpleCreator


def fetch_url_from_websocket(websocket: fastapi.WebSocket) -> str:
    assert isinstance(websocket, fastapi.WebSocket)
    return websocket.url.path


app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
session_factory = providers.Factory(Scope.SESSION, DependentCreator, dep1=app_factory.cast)
request_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)
fastapi_websocket_provider = providers.ContextProvider(Scope.SESSION, fastapi.WebSocket)
websocket_path = providers.Factory(Scope.SESSION, fetch_url_from_websocket, websocket=fastapi_websocket_provider.cast)


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
        session_container: typing.Annotated[AsyncContainer, fastapi.Depends(build_di_container)],
    ) -> None:
        async with session_container.build_child_container() as request_container:
            request_factory_instance = await request_container.resolve_provider(request_factory)
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
        path: typing.Annotated[str, FromDI(websocket_path)],
    ) -> None:
        assert path == "/ws"

        await websocket.accept()
        await websocket.send_text("test")
        await websocket.close()

    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_text()
        assert data == "test"
