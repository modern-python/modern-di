import typing

import fastapi
import modern_di_fastapi
import pytest
from starlette.testclient import TestClient


@pytest.fixture
async def app() -> fastapi.FastAPI:
    app_ = fastapi.FastAPI()
    modern_di_fastapi.setup_di(app_)
    return app_


@pytest.fixture
def client(app: fastapi.FastAPI) -> typing.Iterator[TestClient]:
    with TestClient(app=app) as test_client:
        yield test_client
