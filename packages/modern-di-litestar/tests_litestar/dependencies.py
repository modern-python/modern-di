import dataclasses
import typing

import litestar
from modern_di import Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


def fetch_method_from_request(request: litestar.Request[typing.Any, typing.Any, typing.Any]) -> str:
    assert isinstance(request, litestar.Request)
    return request.method


def fetch_url_from_websocket(websocket: litestar.WebSocket[typing.Any, typing.Any, typing.Any]) -> str:
    assert isinstance(websocket, litestar.WebSocket)
    return websocket.url.path


class Dependencies(Group):
    app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
    session_factory = providers.Factory(Scope.SESSION, DependentCreator, dep1=app_factory.cast).bind_type(None)
    request_factory = providers.Singleton(Scope.REQUEST, DependentCreator, dep1=app_factory.cast).bind_type(None)
    action_factory = providers.Factory(Scope.ACTION, DependentCreator, dep1=app_factory.cast).bind_type(None)
    litestar_request_provider = providers.ContextProvider(Scope.REQUEST, litestar.Request)
    request_method = providers.Factory(
        Scope.REQUEST, fetch_method_from_request, request=litestar_request_provider.cast
    ).bind_type(None)
    litestar_websocket_provider = providers.ContextProvider(Scope.SESSION, litestar.WebSocket)
    websocket_path = providers.Factory(
        Scope.SESSION, fetch_url_from_websocket, websocket=litestar_websocket_provider.cast
    ).bind_type(None)
