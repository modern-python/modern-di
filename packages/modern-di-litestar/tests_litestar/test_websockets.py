import litestar
from litestar.testing import TestClient


async def test_websocket_not_supported(client: TestClient[litestar.Litestar], app: litestar.Litestar) -> None:
    async def websocket_handler(data: str) -> None:
        pass

    app.register(litestar.websocket_listener("/ws")(websocket_handler))

    with client.websocket_connect("/ws") as websocket:
        websocket.send("test")
