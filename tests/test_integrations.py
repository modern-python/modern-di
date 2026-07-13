from modern_di import Scope, providers
from modern_di.integrations import ConnectionMatch, bind, classify_connection


class _Request:
    pass


def test_bind_derives_scope_and_context_from_provider() -> None:
    provider = providers.ContextProvider(_Request, scope=Scope.REQUEST)
    connection = _Request()

    match = bind(provider, connection)

    assert match == ConnectionMatch(scope=Scope.REQUEST, context={_Request: connection})


class _WebSocket:
    pass


def test_classify_connection_dispatches_to_first_isinstance_match() -> None:
    request_provider = providers.ContextProvider(_Request, scope=Scope.REQUEST)
    websocket_provider = providers.ContextProvider(_WebSocket, scope=Scope.SESSION)
    ws = _WebSocket()

    match = classify_connection(ws, (request_provider, websocket_provider))

    assert match == ConnectionMatch(scope=Scope.SESSION, context={_WebSocket: ws})


def test_classify_connection_returns_none_when_nothing_matches() -> None:
    request_provider = providers.ContextProvider(_Request, scope=Scope.REQUEST)

    assert classify_connection(object(), (request_provider,)) is None


def test_classify_connection_first_provider_wins_on_ambiguous_match() -> None:
    class _Sub(_Request):
        pass

    base_provider = providers.ContextProvider(_Request, scope=Scope.REQUEST)
    sub_provider = providers.ContextProvider(_Sub, scope=Scope.SESSION)
    conn = _Sub()

    match = classify_connection(conn, (base_provider, sub_provider))

    assert match == ConnectionMatch(scope=Scope.REQUEST, context={_Request: conn})
