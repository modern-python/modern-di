import typing

import fastapi
from modern_di import Scope, providers
from starlette.testclient import TestClient

from modern_di_fastapi import Provide
from tests.dependencies import DependentCreator, SimpleCreator


app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
session_factory = providers.Factory(Scope.SESSION, DependentCreator, dep1=app_factory.cast)
request_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)


async def test_factories(client: TestClient, app: fastapi.FastAPI) -> None:
    @app.websocket("/ws")
    async def websocket_endpoint(
        websocket: fastapi.WebSocket,
        app_factory_instance: typing.Annotated[SimpleCreator, Provide(app_factory)],
        session_factory_instance: typing.Annotated[DependentCreator, Provide(session_factory)],
    ) -> None:
        assert isinstance(app_factory_instance, SimpleCreator)
        assert isinstance(session_factory_instance, DependentCreator)
        assert session_factory_instance.dep1 is not app_factory_instance

        await websocket.accept()
        await websocket.send_json({"msg": "Hello WebSocket"})
        await websocket.close()

    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_json()
        assert data == {"msg": "Hello WebSocket"}
