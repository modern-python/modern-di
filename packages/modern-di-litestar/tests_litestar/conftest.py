import typing

import litestar
import modern_di_litestar
import pytest
from litestar.testing import TestClient
from modern_di import Container

from tests_litestar.dependencies import Dependencies


@pytest.fixture
async def app() -> litestar.Litestar:
    return litestar.Litestar(debug=True, plugins=[modern_di_litestar.ModernDIPlugin(Container(groups=[Dependencies]))])


@pytest.fixture
def client(app: litestar.Litestar) -> typing.Iterator[TestClient[litestar.Litestar]]:
    with TestClient(app=app, raise_server_exceptions=True) as client:
        yield client
