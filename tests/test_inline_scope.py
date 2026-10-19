import dataclasses

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import ProviderScopeFrozenError, ValidationFailedError


class _Session: ...


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class _Request:
    user: str


class _Handler:
    def __init__(self, session: _Session) -> None:
        self.session = session


def _sessions_of_two_requests(container: Container) -> tuple[_Session, _Session]:
    with container.build_child_container(scope=Scope.REQUEST) as first:
        a = first.resolve(_Handler).session
    with container.build_child_container(scope=Scope.REQUEST) as second:
        b = second.resolve(_Handler).session
    return a, b


def test_inline_cached_factory_takes_group_default_scope() -> None:
    class Dependencies(Group, scope=Scope.REQUEST):
        handler = providers.Factory(_Handler, kwargs={"session": providers.Factory(_Session, cache=True)})

    a, b = _sessions_of_two_requests(Container(groups=[Dependencies]))

    assert a is not b


def test_inline_cached_factory_takes_explicit_parent_scope() -> None:
    class Dependencies(Group):
        handler = providers.Factory(
            _Handler, scope=Scope.REQUEST, kwargs={"session": providers.Factory(_Session, cache=True)}
        )

    a, b = _sessions_of_two_requests(Container(groups=[Dependencies]))

    assert a is not b


def test_inline_factory_over_request_source_validates_and_resolves() -> None:
    class Dependencies(Group, scope=Scope.REQUEST):
        request = providers.ContextProvider(_Request)
        user_name = providers.Factory(
            str, kwargs={"object": providers.Factory(lambda r: r.user, kwargs={"r": request})}
        )

    container = Container(groups=[Dependencies])
    container.validate()

    with container.build_child_container(scope=Scope.REQUEST, context={_Request: _Request(user="alice")}) as child:
        assert child.resolve_provider(Dependencies.user_name) == "alice"


def test_inline_context_provider_reads_request_context() -> None:
    class Dependencies(Group, scope=Scope.REQUEST):
        user = providers.Factory(lambda r: r.user, kwargs={"r": providers.ContextProvider(_Request)})

    container = Container(groups=[Dependencies])

    with container.build_child_container(scope=Scope.REQUEST, context={_Request: _Request(user="alice")}) as child:
        assert child.resolve_provider(Dependencies.user) == "alice"


class _Engine:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn


class _DbConnection:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn


def test_inline_provider_shared_by_app_and_request_parents_takes_app_scope() -> None:
    dsn = providers.Factory(lambda: "postgres://")

    class Dependencies(Group):
        db_connection = providers.Factory(_DbConnection, scope=Scope.REQUEST, kwargs={"dsn": dsn})
        engine = providers.Factory(_Engine, kwargs={"dsn": dsn}, cache=True)

    container = Container(groups=[Dependencies])
    container.validate()

    assert dsn.scope is Scope.APP
    with container.build_child_container(scope=Scope.REQUEST) as child:
        assert child.resolve(_DbConnection).dsn == child.resolve(_Engine).dsn == "postgres://"


def test_inline_provider_scope_is_fixed_at_first_registration() -> None:
    dsn = providers.Factory(lambda: "postgres://")

    class Dependencies(Group):
        db_connection = providers.Factory(_DbConnection, scope=Scope.REQUEST, kwargs={"dsn": dsn})

    container = Container(groups=[Dependencies])
    container.add_providers(providers.Factory(_Engine, kwargs={"dsn": dsn}, cache=True))

    assert dsn.scope is Scope.REQUEST
    with pytest.raises(ValidationFailedError, match="InvalidScopeDependencyError"):
        container.validate()


def test_inline_provider_with_explicit_scope_keeps_it() -> None:
    class Dependencies(Group, scope=Scope.REQUEST):
        handler = providers.Factory(
            _Handler, kwargs={"session": providers.Factory(_Session, scope=Scope.APP, cache=True)}
        )

    a, b = _sessions_of_two_requests(Container(groups=[Dependencies]))

    assert a is b


def test_class_attribute_of_another_group_keeps_its_scope() -> None:
    class Shared(Group):
        session = providers.Factory(_Session, cache=True)

    class Dependencies(Group, scope=Scope.REQUEST):
        handler = providers.Factory(_Handler, kwargs={"session": Shared.session})

    a, b = _sessions_of_two_requests(Container(groups=[Shared, Dependencies]))

    assert Shared.session.scope is Scope.APP
    assert a is b


class _Outer:
    def __init__(self, handler: _Handler) -> None:
        self.handler = handler


def test_provider_inline_in_an_inline_provider_takes_the_scope_down_the_chain() -> None:
    class Dependencies(Group, scope=Scope.REQUEST):
        outer = providers.Factory(
            _Outer,
            kwargs={
                "handler": providers.Factory(_Handler, kwargs={"session": providers.Factory(_Session, cache=True)})
            },
        )

    container = Container(groups=[Dependencies])
    with container.build_child_container(scope=Scope.REQUEST) as first:
        a = first.resolve(_Outer).handler.session
    with container.build_child_container(scope=Scope.REQUEST) as second:
        b = second.resolve(_Outer).handler.session

    assert a is not b


def test_group_cannot_change_scope_of_registered_inline_provider() -> None:
    session = providers.Factory(_Session, cache=True)

    class Dependencies(Group, scope=Scope.REQUEST):
        handler = providers.Factory(_Handler, kwargs={"session": session})

    Container(groups=[Dependencies])

    with pytest.raises(ProviderScopeFrozenError, match="Later"):

        class Later(Group, scope=Scope.SESSION):
            shared_session = session

    assert session.scope is Scope.REQUEST


def test_inline_source_of_inline_derived_provider_takes_parent_scope() -> None:
    class Dependencies(Group, scope=Scope.REQUEST):
        handler = providers.Factory(
            _Handler, kwargs={"session": providers.Factory(_Session, cache=True).derive(lambda s: s)}
        )

    a, b = _sessions_of_two_requests(Container(groups=[Dependencies]))

    assert a is not b
