import datetime

from modern_di import Container, Scope, providers


context_provider = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)
request_context_provider = providers.ContextProvider(scope=Scope.REQUEST, context_type=datetime.datetime)


def test_context_provider() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    app_container = Container(context={datetime.datetime: now})
    app_container.validate_provider(context_provider)
    instance1 = app_container.resolve_provider(context_provider)
    instance2 = app_container.resolve_provider(context_provider)
    assert instance1 is instance2 is now


def test_context_provider_set_context_after_creation() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    app_container = Container()
    app_container.set_context(datetime.datetime, now)
    instance1 = app_container.resolve_provider(context_provider)
    instance2 = app_container.resolve_provider(context_provider)
    assert instance1 is instance2 is now


def test_context_provider_not_found() -> None:
    app_container = Container()
    assert app_container.resolve_provider(context_provider) is None


def test_context_provider_in_request_scope() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    app_container = Container()
    request_container = app_container.build_child_container(context={datetime.datetime: now}, scope=Scope.REQUEST)
    instance1 = request_container.resolve_provider(request_context_provider)
    instance2 = request_container.resolve_provider(request_context_provider)
    assert instance1 is instance2 is now
