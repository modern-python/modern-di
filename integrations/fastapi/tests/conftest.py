import contextlib
import typing

import fastapi
import httpx
import pytest
from asgi_lifespan import LifespanManager

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
def client(app: fastapi.FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
