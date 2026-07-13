import typing

from modern_di import Container, Group, Scope, providers
from modern_di.integrations import (
    ConnectionMatch,
    Marker,
    bind,
    classify_connection,
    from_di,
    parse_markers,
    resolve_markers,
)


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


class _Service:
    pass


class _Deps(Group):
    service = providers.Factory(creator=_Service, scope=Scope.APP)


def test_marker_resolve_delegates_to_container_resolve_dependency() -> None:
    container = Container(groups=[_Deps], validate=True)
    marker: Marker[_Service] = Marker(_Service)

    resolved = marker.resolve(container)

    assert isinstance(resolved, _Service)


def test_from_di_returns_a_marker_cast_as_the_dependency_type() -> None:
    result = from_di(_Service)

    assert isinstance(result, Marker)
    assert result.dependency is _Service


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


def test_parse_markers_finds_annotated_marker_params() -> None:
    marker = Marker(_Service)

    def handler(a: int, b: typing.Annotated[_Service, marker], *, c: str = "x") -> None:
        pass  # pragma: no cover

    assert parse_markers(handler) == {"b": marker}


def test_parse_markers_skips_return_annotation() -> None:
    marker = Marker(_Service)

    def handler() -> typing.Annotated[_Service, marker]:
        raise NotImplementedError  # pragma: no cover

    assert parse_markers(handler) == {}


def test_parse_markers_first_marker_wins_per_parameter() -> None:
    first = Marker(_Service)
    second: Marker[int] = Marker(int)

    def handler(a: typing.Annotated[_Service, first, second]) -> None:
        pass  # pragma: no cover

    assert parse_markers(handler) == {"a": first}


def test_parse_markers_returns_empty_dict_when_no_markers() -> None:
    def handler(a: int) -> None:
        pass  # pragma: no cover

    assert parse_markers(handler) == {}


def test_resolve_markers_resolves_each_marker_by_name() -> None:
    container = Container(groups=[_Deps], validate=True)
    markers = {"service": Marker(_Service)}

    resolved = resolve_markers(container, markers)

    assert isinstance(resolved["service"], _Service)


def test_resolve_markers_empty_input_returns_empty_dict() -> None:
    container = Container(groups=[_Deps], validate=True)

    assert resolve_markers(container, {}) == {}
