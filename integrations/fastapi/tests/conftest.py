import contextlib
import typing

import fastapi
import pytest
from asgi_lifespan import LifespanManager
from starlette.testclient import TestClient

from modern_di_fastapi import setup_di


@contextlib.asynccontextmanager
async def lifespan(app_: fastapi.FastAPI) -> typing.AsyncIterator[None]:
    container = setup_di(app_)
    async with container:
        yield


@pytest.fixture
async def app() -> typing.AsyncIterator[fastapi.FastAPI]:
    app_ = fastapi.FastAPI(lifespan=lifespan)
    async with LifespanManager(app_):
        yield app_


@pytest.fixture
def client(app: fastapi.FastAPI) -> TestClient:
    return TestClient(app=app)
