import faststream
import modern_di
import pytest
from faststream.nats import NatsBroker
from modern_di_faststream import setup_di

from tests_faststream.dependencies import Dependencies


@pytest.fixture
async def app() -> faststream.FastStream:
    app_ = faststream.FastStream(NatsBroker())
    setup_di(app_, container=modern_di.AsyncContainer(groups=[Dependencies]))
    return app_
