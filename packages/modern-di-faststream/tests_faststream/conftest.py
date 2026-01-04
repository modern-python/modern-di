import faststream
import pytest
from faststream.nats import NatsBroker
from modern_di import Container
from modern_di_faststream import setup_di

from tests_faststream.dependencies import Dependencies


@pytest.fixture
async def app() -> faststream.FastStream:
    app_ = faststream.FastStream(NatsBroker())
    setup_di(app_, container=Container(groups=[Dependencies]))
    return app_
