import contextlib
import typing

import faststream
import pytest
from faststream import ContextRepo
from faststream.nats import NatsBroker
from modern_di_faststream import setup_di


@contextlib.asynccontextmanager
async def lifespan(context: ContextRepo) -> typing.AsyncIterator[None]:
    app: faststream.FastStream = context.get("app")
    container = setup_di(app)
    async with container:
        yield


@pytest.fixture
async def app() -> faststream.FastStream:
    return faststream.FastStream(broker=NatsBroker(), lifespan=lifespan)
