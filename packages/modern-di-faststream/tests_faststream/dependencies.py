import dataclasses
import typing

from faststream import StreamMessage
from modern_di import Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


def fetch_message_is_processed_from_request(message: StreamMessage[typing.Any]) -> bool:
    return message.processed


class Dependencies(Group):
    app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
    request_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast).bind_type(None)
    action_factory = providers.Factory(Scope.ACTION, DependentCreator, dep1=app_factory.cast).bind_type(None)
    message_provider = providers.ContextProvider(Scope.REQUEST, StreamMessage)
    message_is_processed = providers.Factory(
        Scope.REQUEST, fetch_message_is_processed_from_request, message=message_provider.cast
    )
