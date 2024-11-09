import contextlib
import typing

import litestar
import modern_di_litestar
import pytest
from asgi_lifespan import LifespanManager
from litestar.testing import TestClient


@contextlib.asynccontextmanager
async def lifespan(app_: litestar.Litestar) -> typing.AsyncIterator[None]:
    container = modern_di_litestar.setup_di(app_)
    async with container:
        yield


@pytest.fixture
async def app() -> typing.AsyncIterator[litestar.Litestar]:
    app_ = litestar.Litestar(lifespan=[lifespan], debug=True, dependencies=modern_di_litestar.prepare_di_dependencies())
    async with LifespanManager(app_):  # type: ignore[arg-type]
        yield app_


@pytest.fixture
def client(app: litestar.Litestar) -> typing.Iterator[TestClient[litestar.Litestar]]:
    with TestClient(app=app) as client:
        yield client
