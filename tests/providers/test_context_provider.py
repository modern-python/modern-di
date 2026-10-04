import dataclasses
import datetime
import typing
import warnings

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import (
    ContainerClosedError,
    ContextValueNotSetError,
    ScopeNotInitializedError,
)
from modern_di.providers.abstract import AbstractProvider


request_context_provider = providers.ContextProvider(scope=Scope.REQUEST, context_type=datetime.datetime)


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SomeFactory:
    arg1: datetime.datetime


class MyGroup(Group):
    context_provider = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)
    some_factory = providers.Factory(creator=SomeFactory)


def test_context_provider() -> None:
    now = datetime.datetime.now(tz=datetime.UTC)
    app_container = Container(groups=[MyGroup], context={datetime.datetime: now})
    app_container.open()
    instance1 = app_container.resolve_provider(MyGroup.context_provider)
    instance2 = app_container.resolve_provider(MyGroup.context_provider)
    assert instance1 is instance2 is now


def test_context_provider_set_context_after_creation() -> None:
    now = datetime.datetime.now(tz=datetime.UTC)
    app_container = Container()
    app_container.open()
    app_container.set_context(datetime.datetime, now)
    instance1 = app_container.resolve_provider(MyGroup.context_provider)
    instance2 = app_container.resolve_provider(MyGroup.context_provider)
    assert instance1 is instance2 is now


def test_context_provider_not_found() -> None:
    app_container = Container()
    app_container.open()
    with pytest.raises(ContextValueNotSetError) as exc_info:
        app_container.resolve_provider(MyGroup.context_provider)
    assert exc_info.value.context_type is datetime.datetime


def test_context_provider_not_found_but_required() -> None:
    app_container = Container(groups=[MyGroup])
    app_container.open()
    with pytest.raises(
        ContextValueNotSetError,
        match=r"No context value is set for <class 'datetime.datetime'> \(scope APP\), needed for argument arg1",
    ) as exc:
        app_container.resolve(SomeFactory)
    assert exc.value.arg_name == "arg1"
    assert exc.value.context_type is datetime.datetime


def test_context_provider_in_request_scope() -> None:
    now = datetime.datetime.now(tz=datetime.UTC)
    app_container = Container()
    app_container.open()
    request_container = app_container.build_child_container(context={datetime.datetime: now}, scope=Scope.REQUEST)
    request_container.open()
    instance1 = request_container.resolve_provider(request_context_provider)
    instance2 = request_container.resolve_provider(request_context_provider)
    assert instance1 is instance2 is now


def test_context_provider_repr() -> None:
    provider = providers.ContextProvider(context_type=str, scope=Scope.REQUEST)
    assert repr(provider) == "ContextProvider(context_type=<class 'str'>, scope=<Scope.REQUEST: 3>)"


def test_context_provider_exposes_context_type() -> None:
    provider = providers.ContextProvider(context_type=datetime.datetime, scope=Scope.REQUEST)
    assert provider.context_type is datetime.datetime


def test_context_provider_has_no_definition_site() -> None:
    provider = providers.ContextProvider(context_type=datetime.datetime, scope=Scope.REQUEST)
    assert provider.definition_site is None


@pytest.mark.parametrize("value", [0, False, "", [], {}, 0.0])
def test_context_provider_returns_falsy_values(value: object) -> None:
    context_type = type(value)
    provider = providers.ContextProvider(scope=Scope.APP, context_type=context_type)
    app_container = Container(context={context_type: value})
    app_container.open()
    assert app_container.resolve_provider(provider) == value


def test_factory_resolves_with_falsy_context_value() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
    class FlagConsumer:
        flag: bool

    class FlagGroup(Group):
        flag_provider = providers.ContextProvider(scope=Scope.APP, context_type=bool)
        consumer = providers.Factory(creator=FlagConsumer)

    app_container = Container(groups=[FlagGroup], context={bool: False})
    app_container.open()
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
    app_container.open()
    instance = app_container.resolve(NoneHolder)
    assert instance.value is None


def test_factory_with_creator_default_raises_when_context_provider_value_unset() -> None:
    default = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)

    @dataclasses.dataclass(kw_only=True, slots=True)
    class TsHolder:
        ts: datetime.datetime = default

    class TsGroup(Group):
        ctx = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)
        holder = providers.Factory(creator=TsHolder)

    class TsDefaultGroup(Group):
        ctx = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime, default=default)
        holder = providers.Factory(creator=TsHolder)

    app_container = Container(groups=[TsGroup])
    app_container.open()
    with pytest.raises(ContextValueNotSetError) as exc:
        app_container.resolve(TsHolder)
    assert exc.value.arg_name == "ts"

    defaulted = Container(groups=[TsDefaultGroup])
    defaulted.open()
    assert defaulted.resolve(TsHolder).ts == default


class _LateCtx: ...


class _NeedsLateCtx:
    def __init__(self, ctx: _LateCtx | None = None) -> None:
        self.ctx = ctx


class _LateCtxGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=_LateCtx, default=None)
    svc = providers.Factory(scope=Scope.APP, creator=_NeedsLateCtx)


def test_set_context_after_first_resolve_is_seen_by_later_resolves() -> None:
    """INVARIANT: a ContextProvider dependency is read live on every resolve.

    Only the *binding* is frozen at compile time, never the value. Caching the value would make a
    later `set_context` invisible to non-cached factories across scopes.
    """
    container = Container(scope=Scope.APP, groups=[_LateCtxGroup])
    container.open()
    first = container.resolve(_NeedsLateCtx)
    assert first.ctx is None  # context unset, default applied
    value = _LateCtx()
    container.set_context(_LateCtx, value)
    second = container.resolve(_NeedsLateCtx)
    assert second.ctx is value


def test_context_provider_through_closed_owning_container_raises() -> None:
    now = datetime.datetime.now(tz=datetime.UTC)
    app = Container(groups=[MyGroup], context={datetime.datetime: now})
    app.open()
    child = app.build_child_container(scope=Scope.REQUEST)
    child.open()
    app.close_sync()
    with pytest.raises(ContainerClosedError) as exc:
        child.resolve_provider(MyGroup.context_provider)
    assert exc.value.container_scope is Scope.APP
    assert app.closed is True
    app.open()
    assert child.resolve_provider(MyGroup.context_provider) == now


# Q-12 — ContextProvider reads the registry at its OWN scope


class _ScopedCtx: ...


class _ScopedCtxGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=_ScopedCtx)


def test_context_provider_reads_registry_at_its_own_scope_not_resolving_container() -> None:
    value = _ScopedCtx()
    app = Container(scope=Scope.APP, groups=[_ScopedCtxGroup])
    app.open()
    request = app.build_child_container(scope=Scope.REQUEST, context={_ScopedCtx: _ScopedCtx()})
    request.open()
    # context set on the CHILD must be invisible to an APP-scoped provider
    with pytest.raises(ContextValueNotSetError) as exc_info:
        request.resolve(_ScopedCtx)
    assert exc_info.value.context_type is _ScopedCtx
    # context set on the container at the provider's scope is what counts
    app.set_context(_ScopedCtx, value)
    assert request.resolve(_ScopedCtx) is value


# --- set_context cross-scope staleness (2026-06-14 deep audit) ---
#
# An APP-scoped ContextProvider consumed by a deeper (REQUEST) scoped Factory:
# the factory's compiled kwargs live in the request child's cache_registry, so a
# late app.set_context must still be picked up by subsequent resolves from that
# child. Context values are resolved live, not baked in at first resolve.


class _CrossCtx: ...


class _CrossDefaultSvc:
    def __init__(self, ctx: _CrossCtx | None = None) -> None:
        self.ctx = ctx


class _CrossNullableSvc:
    def __init__(self, ctx: _CrossCtx | None) -> None:
        self.ctx = ctx


class _CrossRequiredSvc:
    def __init__(self, ctx: _CrossCtx) -> None:
        self.ctx = ctx


class _CrossDefaultGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=_CrossCtx, default=None)
    svc = providers.Factory(scope=Scope.REQUEST, creator=_CrossDefaultSvc)


class _CrossNullableGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=_CrossCtx, default=None)
    svc = providers.Factory(scope=Scope.REQUEST, creator=_CrossNullableSvc)


class _CrossRequiredGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=_CrossCtx)
    svc = providers.Factory(scope=Scope.REQUEST, creator=_CrossRequiredSvc)


def test_late_app_context_seen_by_request_factory_defaulted_param() -> None:
    app = Container(scope=Scope.APP, groups=[_CrossDefaultGroup])
    app.open()
    request = app.build_child_container(scope=Scope.REQUEST)
    request.open()
    assert request.resolve(_CrossDefaultSvc).ctx is None  # context unset at first resolve
    value = _CrossCtx()
    app.set_context(_CrossCtx, value)
    assert request.resolve(_CrossDefaultSvc).ctx is value  # picked up live across scopes


def test_late_app_context_seen_by_request_factory_nullable_param() -> None:
    app = Container(scope=Scope.APP, groups=[_CrossNullableGroup])
    app.open()
    request = app.build_child_container(scope=Scope.REQUEST)
    request.open()
    assert request.resolve(_CrossNullableSvc).ctx is None
    value = _CrossCtx()
    app.set_context(_CrossCtx, value)
    assert request.resolve(_CrossNullableSvc).ctx is value


def test_late_app_context_required_param_raises_then_resolves_across_scopes() -> None:
    app = Container(scope=Scope.APP, groups=[_CrossRequiredGroup])
    app.open()
    request = app.build_child_container(scope=Scope.REQUEST)
    request.open()
    with pytest.raises(ContextValueNotSetError) as exc:
        request.resolve(_CrossRequiredSvc)
    assert exc.value.arg_name == "ctx"
    value = _CrossCtx()
    app.set_context(_CrossCtx, value)
    assert request.resolve(_CrossRequiredSvc).ctx is value


def test_override_of_context_param_applies_after_first_resolve_across_scopes() -> None:
    app = Container(scope=Scope.APP, groups=[_CrossDefaultGroup])
    app.open()
    request = app.build_child_container(scope=Scope.REQUEST)
    request.open()
    assert request.resolve(_CrossDefaultSvc).ctx is None
    override_value = _CrossCtx()
    app.override(_CrossDefaultGroup.ctx, override_value)
    assert request.resolve(_CrossDefaultSvc).ctx is override_value


class _CachedCtxSvc:
    def __init__(self, ctx: _CrossCtx | None = None) -> None:
        self.ctx = ctx


class _CachedCtxGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=_CrossCtx, default=None)
    svc = providers.Factory(scope=Scope.APP, creator=_CachedCtxSvc, cache=True)


def test_late_context_does_not_rebuild_cached_singleton() -> None:
    """INVARIANT: a cached factory is built once and does not re-read a later context value.

    This is the deliberate boundary on live context: caching wins. Making the cached path re-read
    would turn `cache=True` into a per-resolve check.
    """
    app = Container(scope=Scope.APP, groups=[_CachedCtxGroup])
    app.open()
    first = app.resolve(_CachedCtxSvc)
    assert first.ctx is None
    app.set_context(_CrossCtx, _CrossCtx())
    second = app.resolve(_CachedCtxSvc)
    assert second is first
    assert second.ctx is None


def test_cached_factory_injects_present_context_at_cold_build() -> None:
    # Context set before the first (cold) build is injected into the cached instance.
    app = Container(scope=Scope.APP, groups=[_CachedCtxGroup])
    app.open()
    ctx = _CrossCtx()
    app.set_context(_CrossCtx, ctx)
    svc = app.resolve(_CachedCtxSvc)
    assert svc.ctx is ctx


def test_direct_resolve_unset_context_raises() -> None:
    app_container = Container(groups=[MyGroup])
    app_container.open()
    with pytest.raises(ContextValueNotSetError) as exc_info:
        app_container.resolve_provider(MyGroup.context_provider)
    assert exc_info.value.context_type is datetime.datetime


def test_set_context_provider_direct_resolve_does_not_warn() -> None:
    now = datetime.datetime.now(tz=datetime.UTC)
    app_container = Container(groups=[MyGroup], context={datetime.datetime: now})
    app_container.open()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert app_container.resolve_provider(MyGroup.context_provider) is now


def test_context_provider_accepts_positional_context_type() -> None:
    provider = providers.ContextProvider(datetime.datetime)
    now = datetime.datetime.now(tz=datetime.UTC)
    app_container = Container(context={datetime.datetime: now})
    app_container.open()
    assert app_container.resolve_provider(provider) is now


def test_context_provider_rejects_context_type_passed_twice() -> None:
    with pytest.raises(TypeError, match="context_type"):
        providers.ContextProvider(datetime.datetime, context_type=datetime.datetime)  # ty: ignore[parameter-already-assigned]


def test_context_provider_override_direct_short_circuits() -> None:
    # An override of a ContextProvider compiles to a constant resolver, so resolving it directly
    # returns the override with no ContextValueNotSetError, even with nothing in the registry.
    override_value = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)
    app_container = Container(groups=[MyGroup])
    app_container.open()
    app_container.override(MyGroup.context_provider, override_value)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert app_container.resolve_provider(MyGroup.context_provider) is override_value


_SENTINEL_DEFAULT = datetime.datetime(1999, 9, 9, tzinfo=datetime.UTC)


def _ctx_default_creator(*, ctx: datetime.datetime | None = _SENTINEL_DEFAULT) -> str:
    return "default-applied" if ctx is _SENTINEL_DEFAULT else f"got {ctx!r}"


class _KwargsCtxByTypeGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)
    out = providers.Factory(_ctx_default_creator, bound_type=None)


class _KwargsCtxDefaultedGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime, default=_SENTINEL_DEFAULT)
    out = providers.Factory(_ctx_default_creator, bound_type=None, kwargs={"ctx": ctx})


class _KwargsCtxExplicitGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)
    out = providers.Factory(_ctx_default_creator, bound_type=None, kwargs={"ctx": ctx})


def test_kwargs_context_provider_ignores_creator_default_when_unset() -> None:
    app_container = Container(groups=[_KwargsCtxExplicitGroup])
    app_container.open()
    with pytest.raises(ContextValueNotSetError) as exc:
        app_container.resolve_provider(_KwargsCtxExplicitGroup.out)
    assert exc.value.arg_name == "ctx"

    defaulted = Container(groups=[_KwargsCtxDefaultedGroup])
    defaulted.open()
    assert defaulted.resolve_provider(_KwargsCtxDefaultedGroup.out) == "default-applied"


def test_kwargs_context_provider_matches_by_type_wiring() -> None:
    # The same creator wired both ways agrees: how the ContextProvider reaches the parameter is a
    # declaration detail, not a behavior switch.
    by_type = Container(groups=[_KwargsCtxByTypeGroup])
    by_type.open()
    explicit = Container(groups=[_KwargsCtxExplicitGroup])
    explicit.open()
    with pytest.raises(ContextValueNotSetError) as by_type_exc:
        by_type.resolve_provider(_KwargsCtxByTypeGroup.out)
    with pytest.raises(ContextValueNotSetError) as explicit_exc:
        explicit.resolve_provider(_KwargsCtxExplicitGroup.out)
    assert str(by_type_exc.value) == str(explicit_exc.value)


def test_kwargs_context_provider_injects_present_value() -> None:
    now = datetime.datetime.now(tz=datetime.UTC)
    app_container = Container(groups=[_KwargsCtxExplicitGroup], context={datetime.datetime: now})
    app_container.open()
    assert app_container.resolve_provider(_KwargsCtxExplicitGroup.out) == f"got {now!r}"


def test_kwargs_context_provider_override_wins() -> None:
    override_value = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)
    app_container = Container(groups=[_KwargsCtxExplicitGroup])
    app_container.open()
    app_container.override(_KwargsCtxExplicitGroup.ctx, override_value)
    assert app_container.resolve_provider(_KwargsCtxExplicitGroup.out) == f"got {override_value!r}"


def _opaque_ctx_creator(**kw: object) -> str:
    return f"ctx={kw.get('ctx')!r}"


class _KwargsCtxNoSignatureGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)
    out = providers.Factory(_opaque_ctx_creator, bound_type=None, kwargs={"ctx": ctx})


def test_kwargs_context_provider_without_parsed_signature_keeps_direct_resolve() -> None:
    app_container = Container(groups=[_KwargsCtxNoSignatureGroup])
    app_container.open()
    with pytest.raises(ContextValueNotSetError) as exc_info:
        app_container.resolve_provider(_KwargsCtxNoSignatureGroup.out)
    assert exc_info.value.context_type is datetime.datetime
    assert exc_info.value.arg_name == "ctx"


def test_kwargs_context_provider_without_parsed_signature_injects_present_value() -> None:
    # Same no-parsed-signature routing as above, but with a value present: the direct-resolve path
    # returns it normally and the creator runs.
    now = datetime.datetime.now(tz=datetime.UTC)
    app_container = Container(groups=[_KwargsCtxNoSignatureGroup], context={datetime.datetime: now})
    app_container.open()
    assert app_container.resolve_provider(_KwargsCtxNoSignatureGroup.out) == f"ctx={now!r}"


@pytest.mark.parametrize("cache", [False, True])
def test_scope_error_through_a_context_kwarg_carries_one_breadcrumb_step(cache: bool) -> None:
    """INVARIANT: a scope error through a context kwarg carries exactly one breadcrumb step.

    The context provider's resolver calls `find_container`, never the compiler's `_navigate` -- that
    helper prepends a step and the generated resolver prepends the factory's own, so the caller would
    appear twice. Parametrized because the cached and transient templates carry separate handlers.
    """

    class Cfg: ...

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Svc:
        cfg: Cfg

    class G(Group):
        cfg = providers.ContextProvider(Cfg, scope=Scope.REQUEST)
        svc = providers.Factory(creator=Svc, scope=Scope.APP, cache=cache)

    container = Container(scope=Scope.APP, groups=[G])
    container.open()

    with pytest.raises(ScopeNotInitializedError) as exc:
        container.resolve(Svc)

    assert str(exc.value).count("Svc") == 1


def test_context_hop_does_not_call_find_container(monkeypatch: pytest.MonkeyPatch) -> None:
    """INVARIANT: a context kwarg costs no navigation, same-scope or cross-scope.

    The context provider's resolver inlines the scope compare and the ancestor lookup;
    `find_container` runs only when the scope is not an ancestor, to raise. An unconditional call
    adds a frame per context kwarg to the hottest path.
    """

    class Cfg: ...

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Svc:
        cfg: Cfg

    class G(Group):
        cfg = providers.ContextProvider(Cfg, scope=Scope.REQUEST)
        svc = providers.Factory(creator=Svc, scope=Scope.REQUEST)

    app = Container(scope=Scope.APP, groups=[G])
    app.open()
    request = app.build_child_container(scope=Scope.REQUEST, context={Cfg: Cfg()})

    calls: list[object] = []
    original = Container.find_container
    monkeypatch.setattr(Container, "find_container", lambda self, scope: calls.append(scope) or original(self, scope))

    assert isinstance(request.resolve(Svc), Svc)
    assert calls == []

    # The cross-scope hop reads `_scope_map` directly; `find_container` is the miss path only.
    class AppCfg: ...

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Wider:
        app_cfg: AppCfg

    class G2(Group):
        app_cfg = providers.ContextProvider(AppCfg, scope=Scope.APP)
        wider = providers.Factory(creator=Wider, scope=Scope.REQUEST)

    app2 = Container(scope=Scope.APP, groups=[G2], context={AppCfg: AppCfg()})
    app2.open()
    request2 = app2.build_child_container(scope=Scope.REQUEST)

    calls.clear()
    assert isinstance(request2.resolve(Wider), Wider)
    assert calls == []


def test_direct_context_resolve_below_its_scope_raises_scope_error() -> None:
    """A direct resolve of a context provider from a container above its scope takes the miss path."""

    class Cfg: ...

    class G(Group):
        cfg = providers.ContextProvider(Cfg, scope=Scope.REQUEST)

    app = Container(scope=Scope.APP, groups=[G])

    with pytest.raises(ScopeNotInitializedError):
        app.resolve_provider(G.cfg)


class _CachedCtx: ...


@dataclasses.dataclass(kw_only=True, slots=True)
class _CachedNullable:
    ctx: _CachedCtx | None


@dataclasses.dataclass(kw_only=True, slots=True)
class _CachedRequired:
    ctx: _CachedCtx


def test_cached_factory_context_kwarg_uses_override() -> None:
    class G(Group):
        ctx = providers.ContextProvider(_CachedCtx, scope=Scope.APP)
        svc = providers.Factory(creator=_CachedNullable, scope=Scope.APP, cache=True)

    container = Container(scope=Scope.APP, groups=[G])
    container.open()
    sentinel = _CachedCtx()
    container.override(G.ctx, sentinel)
    assert container.resolve(_CachedNullable).ctx is sentinel


def test_transient_factory_context_kwarg_uses_override() -> None:
    class G(Group):
        ctx = providers.ContextProvider(_CachedCtx, scope=Scope.APP)
        svc = providers.Factory(creator=_CachedNullable, scope=Scope.APP)

    container = Container(scope=Scope.APP, groups=[G])
    container.open()
    sentinel = _CachedCtx()
    container.override(G.ctx, sentinel)
    assert container.resolve(_CachedNullable).ctx is sentinel


def test_cached_factory_context_kwarg_absent_and_nullable_injects_the_provider_default() -> None:
    class G(Group):
        ctx = providers.ContextProvider(_CachedCtx, scope=Scope.APP, default=None)
        svc = providers.Factory(creator=_CachedNullable, scope=Scope.APP, cache=True)

    class Required(Group):
        ctx = providers.ContextProvider(_CachedCtx, scope=Scope.APP)
        svc = providers.Factory(creator=_CachedNullable, scope=Scope.APP, cache=True)

    container = Container(scope=Scope.APP, groups=[G])
    container.open()
    assert container.resolve(_CachedNullable).ctx is None

    required = Container(scope=Scope.APP, groups=[Required])
    required.open()
    with pytest.raises(ContextValueNotSetError) as exc:
        required.resolve(_CachedNullable)
    assert exc.value.arg_name == "ctx"


def test_cached_factory_context_kwarg_absent_and_required_raises() -> None:
    class G(Group):
        ctx = providers.ContextProvider(_CachedCtx, scope=Scope.APP)
        svc = providers.Factory(creator=_CachedRequired, scope=Scope.APP, cache=True)

    container = Container(scope=Scope.APP, groups=[G])
    container.open()
    with pytest.raises(ContextValueNotSetError) as exc:
        container.resolve(_CachedRequired)
    assert exc.value.arg_name == "ctx"


def test_cached_factory_context_kwarg_through_closed_holder_raises() -> None:
    class G(Group):
        ctx = providers.ContextProvider(_CachedCtx, scope=Scope.APP)
        svc = providers.Factory(creator=_CachedNullable, scope=Scope.REQUEST, cache=True)

    value = _CachedCtx()
    app = Container(scope=Scope.APP, groups=[G], context={_CachedCtx: value})
    app.open()
    request = app.build_child_container(scope=Scope.REQUEST)
    app.close_sync()

    with pytest.raises(ContainerClosedError):
        request.resolve(_CachedNullable)


def test_transient_factory_context_kwarg_through_closed_holder_raises() -> None:
    class G(Group):
        ctx = providers.ContextProvider(_CachedCtx, scope=Scope.APP)
        svc = providers.Factory(creator=_CachedNullable, scope=Scope.REQUEST)

    value = _CachedCtx()
    app = Container(scope=Scope.APP, groups=[G], context={_CachedCtx: value})
    app.open()
    request = app.build_child_container(scope=Scope.REQUEST)
    app.close_sync()

    with pytest.raises(ContainerClosedError):
        request.resolve(_CachedNullable)


def test_direct_context_resolve_reads_the_scope_only_at_compile_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """INVARIANT: the compiled resolver for a ContextProvider consults `scope` once, at compile time.

    `scope` is a derived property, so reading it per resolve costs ~11ns on a path the marker
    injectors hit once per marker per request. Delegating the lookup back to the provider instead
    of inlining it here reintroduces that read.
    """

    class Cfg: ...

    class G(Group):
        cfg = providers.ContextProvider(Cfg, scope=Scope.REQUEST)

    app = Container(scope=Scope.APP, groups=[G])
    app.open()
    request = app.build_child_container(scope=Scope.REQUEST, context={Cfg: Cfg()})
    assert isinstance(request.resolve(Cfg), Cfg)  # compile the resolver

    reads = 0
    original = AbstractProvider.scope.fget

    def counting_scope(self: providers.ContextProvider[object]) -> object:
        nonlocal reads
        reads += 1
        return original(self)

    monkeypatch.setattr(AbstractProvider, "scope", property(counting_scope))
    assert G.cfg.scope is Scope.REQUEST  # positive control: the counter is wired in
    assert reads == 1

    reads = 0
    assert isinstance(request.resolve(Cfg), Cfg)
    assert reads == 0


def test_unset_context_as_factory_argument_raises_naming_the_parameter() -> None:
    app_container = Container(groups=[MyGroup])
    app_container.open()
    with pytest.raises(ContextValueNotSetError) as exc_info:
        app_container.resolve(SomeFactory)
    assert exc_info.value.context_type is datetime.datetime
    assert exc_info.value.arg_name == "arg1"
    assert "needed for argument arg1" in str(exc_info.value)


def test_direct_resolve_of_unset_context_names_no_parameter() -> None:
    app_container = Container(groups=[MyGroup])
    app_container.open()
    with pytest.raises(ContextValueNotSetError) as exc_info:
        app_container.resolve_provider(MyGroup.context_provider)
    assert exc_info.value.arg_name is None
    assert "needed for argument" not in str(exc_info.value)


_PROVIDER_DEFAULT = datetime.datetime(2001, 1, 1, tzinfo=datetime.UTC)


@pytest.mark.parametrize("default", [None, _PROVIDER_DEFAULT])
def test_context_provider_default_is_returned_when_unset(default: datetime.datetime | None) -> None:
    provider = providers.ContextProvider(datetime.datetime, scope=Scope.APP, default=default)
    app_container = Container()
    app_container.open()
    assert app_container.resolve_provider(provider) is default


@pytest.mark.parametrize("default", [None, _PROVIDER_DEFAULT])
def test_context_provider_default_yields_to_a_set_value(default: datetime.datetime | None) -> None:
    now = datetime.datetime.now(tz=datetime.UTC)
    provider = providers.ContextProvider(datetime.datetime, scope=Scope.APP, default=default)
    app_container = Container(context={datetime.datetime: now})
    app_container.open()
    assert app_container.resolve_provider(provider) is now


@pytest.mark.parametrize("default", [None, _PROVIDER_DEFAULT])
def test_context_provider_default_reaches_a_factory_argument(default: datetime.datetime | None) -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Holder:
        ts: datetime.datetime | None

    class G(Group):
        ts = providers.ContextProvider(datetime.datetime, scope=Scope.APP, default=default)
        holder = providers.Factory(creator=Holder)

    app_container = Container(groups=[G])
    app_container.open()
    assert app_container.resolve(Holder).ts is default
    now = datetime.datetime.now(tz=datetime.UTC)
    app_container.set_context(datetime.datetime, now)
    assert app_container.resolve(Holder).ts is now


class _NamedCtx: ...


@dataclasses.dataclass(kw_only=True, slots=True)
class _NamedInner:
    named: _NamedCtx


@dataclasses.dataclass(kw_only=True, slots=True)
class _NamedOuter:
    inner: _NamedInner


@pytest.mark.parametrize("cache", [False, True])
def test_unset_context_error_names_the_innermost_parameter(cache: bool) -> None:
    class G(Group):
        ctx = providers.ContextProvider(_NamedCtx, scope=Scope.APP)
        inner = providers.Factory(creator=_NamedInner, cache=cache)
        outer = providers.Factory(creator=_NamedOuter, cache=cache)

    app_container = Container(groups=[G])
    app_container.open()
    with pytest.raises(ContextValueNotSetError) as exc_info:
        app_container.resolve(_NamedOuter)
    assert exc_info.value.arg_name == "named"
    assert str(exc_info.value).count("_NamedOuter") == 1
    assert str(exc_info.value).count("_NamedInner") == 1


def test_unset_context_error_names_a_parameter_reached_through_an_alias() -> None:
    class _AliasedCtx: ...

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Holder:
        via_alias: _AliasedCtx

    class G(Group):
        ctx = providers.ContextProvider(_NamedCtx, scope=Scope.APP)
        alias = providers.Alias(_NamedCtx, bound_type=_AliasedCtx)
        holder = providers.Factory(creator=Holder)

    app_container = Container(groups=[G])
    app_container.open()
    with pytest.raises(ContextValueNotSetError) as exc_info:
        app_container.resolve(Holder)
    assert exc_info.value.arg_name == "via_alias"


def test_unset_context_error_skips_a_defaulted_provider_of_the_same_type() -> None:
    def creator(*, optional: _NamedCtx | None, required: _NamedCtx) -> str:
        raise NotImplementedError  # pragma: no cover - the required argument raises first

    optional = providers.ContextProvider(_NamedCtx, scope=Scope.APP, bound_type=None, default=None)

    class G(Group):
        ctx = providers.ContextProvider(_NamedCtx, scope=Scope.APP)
        out = providers.Factory(creator, bound_type=None, kwargs={"optional": optional})

    app_container = Container(groups=[G])
    app_container.open()
    with pytest.raises(ContextValueNotSetError) as exc_info:
        app_container.resolve_provider(G.out)
    assert exc_info.value.arg_name == "required"


class _StandInRequest:
    def __init__(self, method: str) -> None:
        self.method = method


@dataclasses.dataclass(frozen=True, slots=True)
class _Engine:
    name: str


_REPLICA_METHODS = frozenset({"GET"})


def _choose_engine(
    *,
    primary_engine: _Engine,
    replica_engine: _Engine | None,
    request: _StandInRequest | None = None,
) -> _Engine:
    if replica_engine and request and request.method in _REPLICA_METHODS:
        return replica_engine
    return primary_engine


_integration_request_provider = providers.ContextProvider(_StandInRequest, scope=Scope.REQUEST)


class _AppGroup(Group):
    primary_engine = providers.Factory(lambda: _Engine("primary"), bound_type=None)
    replica_engine = providers.Factory(lambda: _Engine("replica"), bound_type=None)
    optional_request = providers.ContextProvider(_StandInRequest, scope=Scope.REQUEST, bound_type=None, default=None)
    dynamic_engine = providers.Factory(
        scope=Scope.REQUEST,
        creator=_choose_engine,
        kwargs={
            "primary_engine": primary_engine,
            "replica_engine": replica_engine,
            "request": optional_request,
        },
    )


def _app_pattern_container() -> Container:
    container = Container(groups=[_AppGroup])
    container.add_providers(_integration_request_provider)
    container.validate()
    return container


def test_app_owned_optional_request_reads_the_integration_request_when_set() -> None:
    request = _StandInRequest("GET")
    child = _app_pattern_container().build_child_container(scope=Scope.REQUEST, context={_StandInRequest: request})
    assert child.resolve_provider(_AppGroup.dynamic_engine) == _Engine("replica")
    assert child.resolve_provider(_AppGroup.optional_request) is request
    assert child.resolve(_StandInRequest) is request


def test_app_owned_optional_request_is_none_when_no_request_is_set() -> None:
    child = _app_pattern_container().build_child_container(scope=Scope.REQUEST)
    assert child.resolve_provider(_AppGroup.dynamic_engine) == _Engine("primary")
    assert child.resolve_provider(_AppGroup.optional_request) is None
    with pytest.raises(ContextValueNotSetError) as exc_info:
        child.resolve(_StandInRequest)
    assert exc_info.value.context_type is _StandInRequest


class _FirstCtx: ...


class _SecondCtx: ...


def _positional_pair(first: _FirstCtx, second: _SecondCtx) -> str:
    raise NotImplementedError  # pragma: no cover - the second argument raises first


def _keyword_pair(*, first: _FirstCtx, second: _SecondCtx) -> str:
    raise NotImplementedError  # pragma: no cover - the second argument raises first


@pytest.mark.parametrize("cache", [False, True])
@pytest.mark.parametrize("creator", [_positional_pair, _keyword_pair])
def test_unset_context_error_names_the_argument_that_failed(creator: typing.Callable[..., str], cache: bool) -> None:
    class G(Group):
        first = providers.ContextProvider(_FirstCtx, scope=Scope.APP)
        second = providers.ContextProvider(_SecondCtx, scope=Scope.APP)
        pair = providers.Factory(creator, bound_type=None, cache=cache)

    app_container = Container(groups=[G], context={_FirstCtx: _FirstCtx()})
    app_container.open()
    with pytest.raises(ContextValueNotSetError) as exc_info:
        app_container.resolve_provider(G.pair)
    assert exc_info.value.context_type is _SecondCtx
    assert exc_info.value.arg_name == "second"


def test_unset_context_error_names_the_failing_one_of_two_same_type_providers() -> None:
    def creator(*, first: _FirstCtx, second: _FirstCtx) -> str:
        raise NotImplementedError  # pragma: no cover - the second argument raises first

    present = providers.ContextProvider(_FirstCtx, scope=Scope.APP, bound_type=None)
    absent = providers.ContextProvider(_FirstCtx, scope=Scope.REQUEST, bound_type=None)

    class G(Group):
        pair = providers.Factory(
            creator, bound_type=None, scope=Scope.REQUEST, kwargs={"first": present, "second": absent}
        )

    app_container = Container(groups=[G], context={_FirstCtx: _FirstCtx()})
    request = app_container.build_child_container(scope=Scope.REQUEST)
    with pytest.raises(ContextValueNotSetError) as exc_info:
        request.resolve_provider(G.pair)
    assert exc_info.value.arg_name == "second"


def test_unset_context_error_names_the_failing_one_of_two_same_type_same_scope_providers() -> None:
    def creator(*, first: _FirstCtx, second: _FirstCtx) -> str:
        raise NotImplementedError  # pragma: no cover - the second argument raises first

    overridden = providers.ContextProvider(_FirstCtx, scope=Scope.APP, bound_type=None)
    unset = providers.ContextProvider(_FirstCtx, scope=Scope.APP, bound_type=None)

    class G(Group):
        pair = providers.Factory(creator, bound_type=None, kwargs={"first": overridden, "second": unset})

    app_container = Container(groups=[G])
    app_container.add_providers(overridden, unset)
    app_container.override(overridden, _FirstCtx())
    with pytest.raises(ContextValueNotSetError) as exc_info:
        app_container.resolve_provider(G.pair)
    assert exc_info.value.arg_name == "second"
