import dataclasses
import datetime

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import ArgumentResolutionError, ContainerClosedError


request_context_provider = providers.ContextProvider(scope=Scope.REQUEST, context_type=datetime.datetime)


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SomeFactory:
    arg1: datetime.datetime


class MyGroup(Group):
    context_provider = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)
    some_factory = providers.Factory(creator=SomeFactory)


def test_context_provider() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    app_container = Container(groups=[MyGroup], context={datetime.datetime: now})
    instance1 = app_container.resolve_provider(MyGroup.context_provider)
    instance2 = app_container.resolve_provider(MyGroup.context_provider)
    assert instance1 is instance2 is now


def test_context_provider_set_context_after_creation() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    app_container = Container()
    app_container.set_context(datetime.datetime, now)
    instance1 = app_container.resolve_provider(MyGroup.context_provider)
    instance2 = app_container.resolve_provider(MyGroup.context_provider)
    assert instance1 is instance2 is now


def test_context_provider_not_found() -> None:
    app_container = Container()
    assert app_container.resolve_provider(MyGroup.context_provider) is None


def test_context_provider_not_found_but_required() -> None:
    app_container = Container(groups=[MyGroup])
    with pytest.raises(
        ArgumentResolutionError, match=r"Argument arg1 of type <class 'datetime.datetime'> cannot be resolved"
    ) as exc:
        app_container.resolve(SomeFactory)
    assert exc.value.arg_name == "arg1"
    assert exc.value.arg_type is datetime.datetime


def test_context_provider_in_request_scope() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    app_container = Container()
    request_container = app_container.build_child_container(context={datetime.datetime: now}, scope=Scope.REQUEST)
    instance1 = request_container.resolve_provider(request_context_provider)
    instance2 = request_container.resolve_provider(request_context_provider)
    assert instance1 is instance2 is now


def test_context_provider_repr() -> None:
    provider = providers.ContextProvider(context_type=str, scope=Scope.REQUEST)
    assert repr(provider) == "ContextProvider(context_type=<class 'str'>, scope=<Scope.REQUEST: 3>)"


@pytest.mark.parametrize("value", [0, False, "", [], {}, 0.0])
def test_context_provider_returns_falsy_values(value: object) -> None:
    context_type = type(value)
    provider = providers.ContextProvider(scope=Scope.APP, context_type=context_type)
    app_container = Container(context={context_type: value})
    assert app_container.resolve_provider(provider) == value


def test_factory_resolves_with_falsy_context_value() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
    class FlagConsumer:
        flag: bool

    class FlagGroup(Group):
        flag_provider = providers.ContextProvider(scope=Scope.APP, context_type=bool)
        consumer = providers.Factory(creator=FlagConsumer)

    app_container = Container(groups=[FlagGroup], context={bool: False})
    instance = app_container.resolve(FlagConsumer)
    assert instance.flag is False


def test_factory_resolves_with_none_context_value() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
    class NoneHolder:
        value: datetime.datetime | None

    class NoneGroup(Group):
        ctx = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)
        holder = providers.Factory(creator=NoneHolder)

    app_container = Container(groups=[NoneGroup], context={datetime.datetime: None})
    instance = app_container.resolve(NoneHolder)
    assert instance.value is None


def test_factory_uses_default_when_context_provider_value_unset() -> None:
    default = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)

    @dataclasses.dataclass(kw_only=True, slots=True)
    class TsHolder:
        ts: datetime.datetime = default

    class TsGroup(Group):
        ctx = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)
        holder = providers.Factory(creator=TsHolder)

    app_container = Container(groups=[TsGroup])
    instance = app_container.resolve(TsHolder)
    assert instance.ts == default


class _LateCtx: ...


class _NeedsLateCtx:
    def __init__(self, ctx: _LateCtx | None = None) -> None:
        self.ctx = ctx


class _LateCtxGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=_LateCtx)
    svc = providers.Factory(scope=Scope.APP, creator=_NeedsLateCtx)


def test_set_context_after_first_resolve_is_seen_by_later_resolves() -> None:
    container = Container(scope=Scope.APP, groups=[_LateCtxGroup])
    first = container.resolve(_NeedsLateCtx)
    assert first.ctx is None  # context unset, default applied
    value = _LateCtx()
    container.set_context(_LateCtx, value)
    second = container.resolve(_NeedsLateCtx)
    assert second.ctx is value


def test_context_provider_through_closed_owning_container_raises() -> None:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    app = Container(groups=[MyGroup], context={datetime.datetime: now})
    child = app.build_child_container(scope=Scope.REQUEST)
    app.close_sync()
    with pytest.raises(ContainerClosedError):
        child.resolve_provider(MyGroup.context_provider)


# Q-12 — ContextProvider reads the registry at its OWN scope


class _ScopedCtx: ...


class _ScopedCtxGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=_ScopedCtx)


def test_context_provider_reads_registry_at_its_own_scope_not_resolving_container() -> None:
    value = _ScopedCtx()
    app = Container(scope=Scope.APP, groups=[_ScopedCtxGroup])
    request = app.build_child_container(scope=Scope.REQUEST, context={_ScopedCtx: _ScopedCtx()})
    # context set on the CHILD must be invisible to an APP-scoped provider
    assert request.resolve(_ScopedCtx) is None
    # context set on the container at the provider's scope is what counts
    app.set_context(_ScopedCtx, value)
    assert request.resolve(_ScopedCtx) is value
