import dataclasses

import fastapi
from modern_di import Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


def fetch_method_from_request(request: fastapi.Request) -> str:
    assert isinstance(request, fastapi.Request)
    return request.method


def fetch_url_from_websocket(websocket: fastapi.WebSocket) -> str:
    assert isinstance(websocket, fastapi.WebSocket)
    return websocket.url.path


class Dependencies(Group):
    app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
    session_factory = providers.Factory(Scope.SESSION, DependentCreator, dep1=app_factory.cast)
    request_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)
    action_factory = providers.Factory(Scope.ACTION, DependentCreator, dep1=app_factory.cast)
    fastapi_request_provider = providers.ContextProvider(Scope.REQUEST, fastapi.Request)
    request_method = providers.Factory(Scope.REQUEST, fetch_method_from_request, request=fastapi_request_provider.cast)
    fastapi_websocket_provider = providers.ContextProvider(Scope.SESSION, fastapi.WebSocket)
    websocket_path = providers.Factory(
        Scope.SESSION, fetch_url_from_websocket, websocket=fastapi_websocket_provider.cast
    )
