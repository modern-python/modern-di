import typing

from faststream import FastStream, TestApp
from faststream.nats import NatsBroker, TestNatsBroker
from modern_di import Scope, providers
from modern_di_faststream import FromDI, setup_di

from tests_faststream.dependencies import DependentCreator, SimpleCreator


broker = NatsBroker()
app = FastStream(broker)
setup_di(app)
TEST_SUBJECT = "test"


app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
request_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)
action_factory = providers.Factory(Scope.ACTION, DependentCreator, dep1=app_factory.cast)


async def test_factories() -> None:
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
