import typing

import litestar
from litestar.testing import TestClient
from modern_di import AsyncContainer, Scope, providers
from modern_di_litestar import FromDI

from tests_litestar.dependencies import DependentCreator, SimpleCreator


def fetch_url_from_websocket(websocket: litestar.WebSocket[typing.Any, typing.Any, typing.Any]) -> str:
    assert isinstance(websocket, litestar.WebSocket)
    return websocket.url.path


app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
session_factory = providers.Factory(Scope.SESSION, DependentCreator, dep1=app_factory.cast)
request_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)
litestar_websocket_provider = providers.ContextProvider(Scope.SESSION, litestar.WebSocket)
websocket_path = providers.Factory(Scope.SESSION, fetch_url_from_websocket, websocket=litestar_websocket_provider.cast)


async def test_factories(client: TestClient[litestar.Litestar], app: litestar.Litestar) -> None:
    @litestar.websocket_listener(
        "/ws",
        dependencies={"app_factory_instance": FromDI(app_factory), "session_factory_instance": FromDI(session_factory)},
    )
    async def websocket_handler(
        data: str,
        app_factory_instance: SimpleCreator,
        session_factory_instance: DependentCreator,
    ) -> None:
        assert data == "test"
        assert isinstance(app_factory_instance, SimpleCreator)
        assert isinstance(session_factory_instance, DependentCreator)
        assert session_factory_instance.dep1 is not app_factory_instance

    app.register(websocket_handler)

    with client.websocket_connect("/ws") as websocket:
        websocket.send("test")


async def test_factories_request_scope(client: TestClient[litestar.Litestar], app: litestar.Litestar) -> None:
    @litestar.websocket_listener("/ws")
    async def websocket_handler(data: str, di_container: AsyncContainer) -> None:
        assert data == "test"
        async with di_container.build_child_container() as request_container:
            request_factory_instance = await request_container.resolve_provider(request_factory)
            assert isinstance(request_factory_instance, DependentCreator)

    app.register(websocket_handler)

    with client.websocket_connect("/ws") as websocket:
        websocket.send("test")


async def test_context_adapter(client: TestClient[litestar.Litestar], app: litestar.Litestar) -> None:
    @litestar.websocket_listener("/ws", dependencies={"path": FromDI(websocket_path)})
    async def websocket_handler(data: str, path: str) -> None:
        assert data == "test"
        assert path == "/ws"

    app.register(websocket_handler)

    with client.websocket_connect("/ws") as websocket:
        websocket.send("test")
