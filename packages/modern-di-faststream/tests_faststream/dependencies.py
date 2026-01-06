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
    app_factory = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "original"})
    request_factory = providers.Factory(scope=Scope.REQUEST, creator=DependentCreator, bound_type=None)
    action_factory = providers.Factory(scope=Scope.ACTION, creator=DependentCreator, bound_type=None)
    message_is_processed = providers.Factory(scope=Scope.REQUEST, creator=fetch_message_is_processed_from_request)
