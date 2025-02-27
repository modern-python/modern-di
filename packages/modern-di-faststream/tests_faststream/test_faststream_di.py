import typing

import faststream
from faststream import TestApp
from faststream.broker.message import StreamMessage
from faststream.nats import NatsBroker, TestNatsBroker
from modern_di import Scope, providers
from modern_di_faststream import FromDI

from tests_faststream.dependencies import DependentCreator, SimpleCreator


TEST_SUBJECT = "test"


def context_adapter_function(*, message: StreamMessage[typing.Any], **_: object) -> bool:
    return message.processed


app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
request_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)
action_factory = providers.Factory(Scope.ACTION, DependentCreator, dep1=app_factory.cast)
context_adapter = providers.ContextAdapter(Scope.REQUEST, context_adapter_function)


async def test_factories(app: faststream.FastStream) -> None:
    broker = typing.cast(NatsBroker, app.broker)

    @broker.subscriber(TEST_SUBJECT)
    async def index_subscriber(
        app_factory_instance: typing.Annotated[SimpleCreator, FromDI(app_factory)],
        request_factory_instance: typing.Annotated[DependentCreator, FromDI(request_factory)],
    ) -> None:
        assert isinstance(app_factory_instance, SimpleCreator)
        assert isinstance(request_factory_instance, DependentCreator)
        assert request_factory_instance.dep1 is not app_factory_instance

    async with TestNatsBroker(broker) as br, TestApp(app):
        result = await br.request(None, TEST_SUBJECT)
        result_str = await result.decode()
        assert result_str == b""


async def test_context_adapter(app: faststream.FastStream) -> None:
    broker = typing.cast(NatsBroker, app.broker)

    @broker.subscriber(TEST_SUBJECT)
    async def index_subscriber(
        processed: typing.Annotated[bool, FromDI(context_adapter)],
    ) -> None:
        assert processed is False

    async with TestNatsBroker(broker) as br, TestApp(app):
        result = await br.request(None, TEST_SUBJECT)
        result_str = await result.decode()
        assert result_str == b""
