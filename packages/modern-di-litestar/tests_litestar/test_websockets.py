import litestar
from litestar.testing import TestClient
from modern_di import Container
from modern_di_litestar import FromDI

from tests_litestar.dependencies import Dependencies, DependentCreator, SimpleCreator


async def test_factories(client: TestClient[litestar.Litestar], app: litestar.Litestar) -> None:
    @litestar.websocket_listener(
        "/ws",
        dependencies={
            "app_factory_instance": FromDI(SimpleCreator),
            "session_factory_instance": FromDI(Dependencies.session_factory),
        },
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
    async def websocket_handler(data: str, di_container: Container) -> None:
        assert data == "test"
        request_container = di_container.build_child_container()
        request_factory_instance = request_container.resolve_provider(Dependencies.request_factory)
        assert isinstance(request_factory_instance, DependentCreator)

    app.register(websocket_handler)

    with client.websocket_connect("/ws") as websocket:
        websocket.send("test")


async def test_context_adapter(client: TestClient[litestar.Litestar], app: litestar.Litestar) -> None:
    @litestar.websocket_listener("/ws", dependencies={"path": FromDI(Dependencies.websocket_path)})
    async def websocket_handler(data: str, path: str) -> None:
        assert data == "test"
        assert path == "/ws"

    app.register(websocket_handler)

    with client.websocket_connect("/ws") as websocket:
        websocket.send("test")
