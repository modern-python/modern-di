import typing

import faststream
import modern_di
import modern_di_faststream
import pytest
from faststream import TestApp
from faststream.broker.message import StreamMessage
from faststream.nats import NatsBroker, TestNatsBroker
from modern_di import Scope, providers
from modern_di_faststream import FromDI

from tests_faststream.dependencies import DependentCreator, SimpleCreator


TEST_SUBJECT = "test"


def fetch_message_is_processed_from_request(message: StreamMessage[typing.Any]) -> bool:
    return message.processed


app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
request_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)
action_factory = providers.Factory(Scope.ACTION, DependentCreator, dep1=app_factory.cast)
message_provider = providers.ContextProvider(Scope.REQUEST, StreamMessage)
message_is_processed = providers.Factory(
    Scope.REQUEST, fetch_message_is_processed_from_request, message=message_provider.cast
)


async def test_factories(app: faststream.FastStream) -> None:
    broker = typing.cast(NatsBroker, app.broker)

    @broker.subscriber(TEST_SUBJECT)
    async def index_subscriber(
        message: str,
        app_factory_instance: typing.Annotated[SimpleCreator, FromDI(app_factory)],
        request_factory_instance: typing.Annotated[DependentCreator, FromDI(request_factory)],
    ) -> None:
        assert message == "test"
        assert isinstance(app_factory_instance, SimpleCreator)
        assert isinstance(request_factory_instance, DependentCreator)
        assert request_factory_instance.dep1 is not app_factory_instance

    async with TestNatsBroker(broker) as br, TestApp(app):
        await br.publish("test", TEST_SUBJECT)


async def test_context_adapter(app: faststream.FastStream) -> None:
    broker = typing.cast(NatsBroker, app.broker)

    @broker.subscriber(TEST_SUBJECT)
    async def index_subscriber(
        message_is_processed: typing.Annotated[bool, FromDI(message_is_processed)],
    ) -> None:
        assert message_is_processed is False

    async with TestNatsBroker(broker) as br, TestApp(app):
        result = await br.request(None, TEST_SUBJECT)
        result_str = await result.decode()
        assert result_str == b""


async def test_app_without_broker() -> None:
    with pytest.raises(RuntimeError, match="Broker must be defined to setup DI"):
        modern_di_faststream.setup_di(faststream.FastStream())


def test_fetch_di_container(app: faststream.FastStream) -> None:
    di_container = modern_di_faststream.fetch_di_container(app)
    assert isinstance(di_container, modern_di.AsyncContainer)
