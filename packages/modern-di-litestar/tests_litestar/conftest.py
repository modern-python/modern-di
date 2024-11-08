import contextlib
import typing

import litestar
import pytest
from asgi_lifespan import LifespanManager
from litestar.testing import TestClient
from modern_di_litestar import setup_di


@contextlib.asynccontextmanager
async def lifespan(app_: litestar.Litestar) -> typing.AsyncIterator[None]:
    container = setup_di(app_)
    async with container:
        yield


@pytest.fixture
async def app() -> typing.AsyncIterator[litestar.Litestar]:
    app_ = litestar.Litestar(lifespan=[lifespan], debug=True)
    async with LifespanManager(app_):  # type: ignore[arg-type]
        yield app_


@pytest.fixture
def client(app: litestar.Litestar) -> typing.Iterator[TestClient[litestar.Litestar]]:
    with TestClient(app=app) as client:
        yield client
