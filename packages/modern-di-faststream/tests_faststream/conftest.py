import faststream
import pytest
from faststream.nats import NatsBroker
from modern_di_faststream import setup_di


@pytest.fixture
async def app() -> faststream.FastStream:
    app_ = faststream.FastStream(broker=NatsBroker())
    setup_di(app_)
    return app_
