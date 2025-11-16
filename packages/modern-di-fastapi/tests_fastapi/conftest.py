import typing

import fastapi
import modern_di
import modern_di_fastapi
import pytest
from starlette.testclient import TestClient

from tests_fastapi.dependencies import Dependencies


@pytest.fixture
async def app() -> fastapi.FastAPI:
    app_ = fastapi.FastAPI()
    container = modern_di.AsyncContainer(groups=[Dependencies])
    modern_di_fastapi.setup_di(app_, container=container)
    return app_


@pytest.fixture
def client(app: fastapi.FastAPI) -> typing.Iterator[TestClient]:
    with TestClient(app=app) as test_client:
        yield test_client
