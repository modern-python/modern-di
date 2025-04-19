import typing

import litestar
import modern_di
import modern_di_litestar
import pytest
from litestar.testing import TestClient


@pytest.fixture
async def app() -> litestar.Litestar:
    return litestar.Litestar(debug=True, plugins=[modern_di_litestar.ModernDIPlugin()])


@pytest.fixture
def di_container(app: litestar.Litestar) -> modern_di.Container:
    return modern_di_litestar.fetch_di_container(app)


@pytest.fixture
def client(app: litestar.Litestar) -> typing.Iterator[TestClient[litestar.Litestar]]:
    with TestClient(app=app) as client:
        yield client
