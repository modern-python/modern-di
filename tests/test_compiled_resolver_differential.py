"""Differential A/B: compiled vs interpreted resolve must be observably identical."""

import contextlib
import dataclasses
import datetime
import sys
import typing
import warnings

import pytest

from modern_di import Container, Group, Scope, exceptions, providers
from modern_di import container as container_mod
from modern_di.resolver_compiler import _positional_names


# Lowering the recursion limit triggers the RecursionError closer to the call site, keeping the
# genuine-cycle case fast and deterministic (see tests/test_runtime_cycle_guard.py for the same
# rationale). Only the xfail cycle test needs it.
_SHALLOW_RECURSION_LIMIT = 80


@contextlib.contextmanager
def forced_interpreted() -> typing.Iterator[None]:
    prior = container_mod._force_interpreted  # noqa: SLF001
    container_mod._force_interpreted = True  # noqa: SLF001
    try:
        yield
    finally:
        container_mod._force_interpreted = prior  # noqa: SLF001


@dataclasses.dataclass(slots=True)
class Dep:
    pass


@dataclasses.dataclass(slots=True)
class Service:
    dep: Dep


@dataclasses.dataclass(slots=True)
class Leaf:
    pass


def boom(dep: Dep) -> "Boom":  # noqa: ARG001 - creator that raises inside its body, never uses dep
    msg = "boom"
    raise ValueError(msg)


@dataclasses.dataclass(slots=True)
class Boom:
    dep: Dep


class G(Group):
    leaf = providers.Factory(creator=Leaf, scope=Scope.APP)
    dep = providers.Factory(creator=Dep, scope=Scope.APP)
    svc = providers.Factory(creator=Service, scope=Scope.APP)
    boom = providers.Factory(creator=boom, scope=Scope.APP)


_Outcome = tuple[str, str]
_OutcomeWithWarnings = tuple[str, str, tuple[str, ...]]


def _resolve_both(
    build_container: typing.Callable[[], Container], provider: "providers.AbstractProvider[typing.Any]"
) -> tuple[_OutcomeWithWarnings, _OutcomeWithWarnings]:
    """Return (compiled_outcome, interpreted_outcome) as ('value'|'error', str, sorted warning names).

    Warnings emitted during the resolve are captured too, so a path that warns (or fails to warn)
    when the other doesn't shows up as a mismatch, not silently.
    """

    def once(interpreted: bool) -> _OutcomeWithWarnings:
        c = build_container()
        ctx = forced_interpreted() if interpreted else contextlib.nullcontext()
        with ctx, warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                outcome: _Outcome = ("value", repr(c.resolve_provider(provider)))
            except Exception as exc:  # noqa: BLE001
                outcome = ("error", f"{type(exc).__name__}: {exc}")
        warning_names = tuple(sorted(type(w.message).__name__ for w in caught))
        return (*outcome, warning_names)

    return once(False), once(True)


def _lifecycle_both(scenario: typing.Callable[[bool], _Outcome]) -> tuple[_Outcome, _Outcome]:
    """Run a lifecycle `scenario` once compiled, once interpreted; return (compiled, interpreted).

    Unlike `_resolve_both`, `scenario` owns its own container build, resolve(s), and close(s) --
    lifecycle cases need fresh per-path state (e.g. a finalizer-order list) rather than a single
    resolve call.
    """
    return scenario(False), scenario(True)


async def _lifecycle_both_async(
    scenario: typing.Callable[[bool], typing.Awaitable[_Outcome]],
) -> tuple[_Outcome, _Outcome]:
    """Async counterpart of `_lifecycle_both`, for scenarios that `await close_async()`."""
    return await scenario(False), await scenario(True)


@pytest.mark.parametrize("provider_name", ["leaf", "dep", "svc", "boom"])
def test_transient_equivalence(provider_name: str) -> None:
    provider = getattr(G, provider_name)
    compiled, interpreted = _resolve_both(lambda: Container(scope=Scope.APP, groups=[G], validate=False), provider)
    assert compiled == interpreted, (provider_name, compiled, interpreted)


@dataclasses.dataclass(slots=True)
class ChainA:
    pass


@dataclasses.dataclass(slots=True)
class ChainB:
    a: ChainA


@dataclasses.dataclass(slots=True)
class ChainC:
    b: ChainB


@dataclasses.dataclass(slots=True)
class ChainD:
    c: ChainC


@dataclasses.dataclass(slots=True)
class ChainE:
    d: ChainD


@dataclasses.dataclass(slots=True)
class ChainF:
    e: ChainE


class ChainGroup(Group):
    a = providers.Factory(creator=ChainA, scope=Scope.APP)
    b = providers.Factory(creator=ChainB, scope=Scope.APP)
    c = providers.Factory(creator=ChainC, scope=Scope.APP)
    d = providers.Factory(creator=ChainD, scope=Scope.APP)
    e = providers.Factory(creator=ChainE, scope=Scope.APP)
    f = providers.Factory(creator=ChainF, scope=Scope.APP)


def test_deep_chain_equivalence() -> None:
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[ChainGroup], validate=False), ChainGroup.f
    )
    assert compiled == interpreted


@dataclasses.dataclass(slots=True)
class W0:
    pass


@dataclasses.dataclass(slots=True)
class W1:
    pass


@dataclasses.dataclass(slots=True)
class W2:
    pass


@dataclasses.dataclass(slots=True)
class W3:
    pass


@dataclasses.dataclass(slots=True)
class W4:
    pass


@dataclasses.dataclass(slots=True)
class W5:
    pass


@dataclasses.dataclass(slots=True)
class W6:
    pass


@dataclasses.dataclass(slots=True)
class W7:
    pass


@dataclasses.dataclass(slots=True)
class W8:
    pass


@dataclasses.dataclass(slots=True)
class W9:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class Wide:
    w0: W0
    w1: W1
    w2: W2
    w3: W3
    w4: W4
    w5: W5
    w6: W6
    w7: W7
    w8: W8
    w9: W9


class WideGroup(Group):
    w0 = providers.Factory(creator=W0, scope=Scope.APP)
    w1 = providers.Factory(creator=W1, scope=Scope.APP)
    w2 = providers.Factory(creator=W2, scope=Scope.APP)
    w3 = providers.Factory(creator=W3, scope=Scope.APP)
    w4 = providers.Factory(creator=W4, scope=Scope.APP)
    w5 = providers.Factory(creator=W5, scope=Scope.APP)
    w6 = providers.Factory(creator=W6, scope=Scope.APP)
    w7 = providers.Factory(creator=W7, scope=Scope.APP)
    w8 = providers.Factory(creator=W8, scope=Scope.APP)
    w9 = providers.Factory(creator=W9, scope=Scope.APP)
    wide = providers.Factory(creator=Wide, scope=Scope.APP)


def test_wide_equivalence() -> None:
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[WideGroup], validate=False), WideGroup.wide
    )
    assert compiled == interpreted


@dataclasses.dataclass(slots=True)
class AppThing:
    pass


@dataclasses.dataclass(slots=True)
class ReqThing:
    app: AppThing


class CrossScopeGroup(Group):
    app_thing = providers.Factory(creator=AppThing, scope=Scope.APP)
    req_thing = providers.Factory(creator=ReqThing, scope=Scope.REQUEST)


def test_cross_scope_equivalence() -> None:
    def build() -> Container:
        app_container = Container(scope=Scope.APP, groups=[CrossScopeGroup], validate=False)
        return app_container.build_child_container(scope=Scope.REQUEST)

    compiled, interpreted = _resolve_both(build, CrossScopeGroup.req_thing)
    assert compiled == interpreted


def test_scope_not_initialized_equivalence() -> None:
    # Resolving a REQUEST-scoped provider directly from the APP container (no child built).
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[CrossScopeGroup], validate=False), CrossScopeGroup.req_thing
    )
    assert compiled == interpreted
    assert compiled[0] == "error"


def test_override_equivalence() -> None:
    def build() -> Container:
        c = Container(scope=Scope.APP, groups=[G], validate=False)
        c.override(G.dep, Dep())
        return c

    compiled, interpreted = _resolve_both(build, G.svc)
    assert compiled == interpreted


@dataclasses.dataclass(kw_only=True, slots=True)
class NeedsContext:
    arg1: datetime.datetime


class RequiredContextGroup(Group):
    needs_context = providers.Factory(creator=NeedsContext, scope=Scope.APP)


def test_context_required_but_absent_equivalence() -> None:
    # A required ContextProvider-backed kwarg with no value set: hits the compiled
    # kwarg-resolution error path (build_kwargs' _STEP_ERRORS branch), not the creator-call path.
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[RequiredContextGroup], validate=False),
        RequiredContextGroup.needs_context,
    )
    assert compiled == interpreted
    assert compiled[0] == "error"


@dataclasses.dataclass(slots=True)
class ViaAlias:
    dep: Dep


class AliasDepGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP)
    via_alias = providers.Factory(creator=ViaAlias, scope=Scope.APP, kwargs={"dep": providers.Alias(source_type=Dep)})


def test_fallback_alias_dep_equivalence() -> None:
    # A Factory depending on an Alias (a non-Factory provider) exercises resolver_for's
    # fallback-thunk branch inside a compiled Factory's provider_kwargs.
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[AliasDepGroup], validate=False), AliasDepGroup.via_alias
    )
    assert compiled == interpreted


@dataclasses.dataclass(slots=True)
class NeedsContainer:
    container: Container


class ContainerProviderDepGroup(Group):
    needs_container = providers.Factory(creator=NeedsContainer, scope=Scope.APP)


def test_fallback_container_provider_dep_equivalence() -> None:
    # A Factory depending on the auto-registered ContainerProvider (a non-Factory provider)
    # exercises the same fallback-thunk branch via a different provider type.
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[ContainerProviderDepGroup], validate=False),
        ContainerProviderDepGroup.needs_container,
    )
    assert compiled == interpreted


class ContextSuccessGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)
    needs_context = providers.Factory(creator=NeedsContext, scope=Scope.APP)


def test_context_present_equivalence() -> None:
    # A required ContextProvider-backed kwarg with a value actually set: the plan is non-pure
    # and resolves successfully, hitting build_kwargs' "not pure" success path on both sides.
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    compiled, interpreted = _resolve_both(
        lambda: Container(
            scope=Scope.APP, groups=[ContextSuccessGroup], validate=False, context={datetime.datetime: now}
        ),
        ContextSuccessGroup.needs_context,
    )
    assert compiled == interpreted


@dataclasses.dataclass(slots=True)
class NoArgs:
    pass


class BindingErrorGroup(Group):
    # An unexpected static kwarg reaches the creator (skip_creator_parsing bypasses signature
    # validation), so creator(**kwargs) raises a *binding* TypeError with no inner frame —
    # exercising the inlined _call_creator's tb_next branch -> CreatorCallError, compared
    # compiled==interpreted. (Distinct from `boom`, whose body raises ValueError.) NoArgs is the
    # creator directly (a dataclass whose __init__ rejects the extra kwarg), so no test-local
    # creator body is left unreachable.
    thing = providers.Factory(
        creator=NoArgs,
        scope=Scope.APP,
        kwargs={"unexpected": 1},
        skip_creator_parsing=True,
        bound_type=NoArgs,
    )


def test_binding_typeerror_equivalence() -> None:
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[BindingErrorGroup], validate=False), BindingErrorGroup.thing
    )
    assert compiled == interpreted
    assert compiled[0] == "error"
    assert "CreatorCallError" in compiled[1]


class BodyTypeError:
    def __init__(self) -> None:
        len(5)  # ty: ignore[invalid-argument-type]  # TypeError inside the body (has an inner frame)


class BodyTypeErrorGroup(Group):
    # The creator's body raises TypeError (inner frame present, tb_next is not None), so both the
    # inlined and interpreted _call_creator must let it propagate UNCHANGED (not wrap it in a
    # CreatorCallError). Complements the binding-TypeError case above (no inner frame -> wrapped).
    thing = providers.Factory(
        creator=BodyTypeError, scope=Scope.APP, bound_type=BodyTypeError, skip_creator_parsing=True
    )


def test_body_typeerror_propagates_equivalence() -> None:
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[BodyTypeErrorGroup], validate=False), BodyTypeErrorGroup.thing
    )
    assert compiled == interpreted
    assert compiled[0] == "error"
    assert compiled[1].startswith("TypeError:")  # propagated unchanged, not wrapped in CreatorCallError


class CachedGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP, cache=True)


def test_cached_equivalence() -> None:
    # A cached (singleton) Factory: exercises the cache_settings-is-not-None compiled branch,
    # and (under forced interpretation) Factory.resolve's cached branch.
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[CachedGroup], validate=False), CachedGroup.dep
    )
    assert compiled == interpreted


class CachedScopeErrorGroup(Group):
    thing = providers.Factory(creator=AppThing, scope=Scope.REQUEST, cache=True)


def test_cached_scope_not_initialized_equivalence() -> None:
    # A cached REQUEST-scoped provider resolved directly from the APP container: exercises the
    # scope-error branch inside the compiled cached resolver specifically (resolve_cached).
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[CachedScopeErrorGroup], validate=False),
        CachedScopeErrorGroup.thing,
    )
    assert compiled == interpreted
    assert compiled[0] == "error"


class WarmCachedGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP, cache=True)


def test_cached_warm_singleton_equivalence() -> None:
    # Resolve twice: the second resolve is a cache hit. Checks value identity within each path
    # (not just repr), then compares the two paths' outcomes against each other.
    def scenario(interpreted: bool) -> _Outcome:
        c = Container(scope=Scope.APP, groups=[WarmCachedGroup], validate=False)
        ctx = forced_interpreted() if interpreted else contextlib.nullcontext()
        with ctx:
            first = c.resolve_provider(WarmCachedGroup.dep)
            second = c.resolve_provider(WarmCachedGroup.dep)
        return ("value", repr((first is second, first)))

    compiled, interpreted = _lifecycle_both(scenario)
    assert compiled == interpreted
    assert compiled == ("value", "(True, Dep())")


@dataclasses.dataclass(kw_only=True, slots=True)
class CachedNeedsContext:
    arg1: datetime.datetime


class CachedContextGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)
    thing = providers.Factory(creator=CachedNeedsContext, scope=Scope.APP, cache=True)


def test_cached_context_kwarg_equivalence() -> None:
    # A cached Factory with a live context-backed kwarg: the cold cached-miss path runs its own
    # build_kwargs helper down the non-pure branch (folding in the resolved context value).
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    compiled, interpreted = _resolve_both(
        lambda: Container(
            scope=Scope.APP, groups=[CachedContextGroup], validate=False, context={datetime.datetime: now}
        ),
        CachedContextGroup.thing,
    )
    assert compiled == interpreted


@dataclasses.dataclass(slots=True)
class ReqOnly:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class CachedNeedsReq:
    req: ReqOnly


class CachedDepStepErrorGroup(Group):
    req = providers.Factory(creator=ReqOnly, scope=Scope.REQUEST)
    thing = providers.Factory(creator=CachedNeedsReq, scope=Scope.APP, cache=True)


def test_cached_dependency_step_error_equivalence() -> None:
    # A cached APP Factory whose dependency is REQUEST-scoped (unvalidated). The cached provider's
    # own scope resolves fine, so the ScopeNotInitializedError is raised while building kwargs --
    # exercising the cached-miss build_kwargs' _STEP_ERRORS/prepend_step branch (not resolve_cached's
    # own find_container guard). Breadcrumb + error str must match compiled==interpreted.
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[CachedDepStepErrorGroup], validate=False),
        CachedDepStepErrorGroup.thing,
    )
    assert compiled == interpreted
    assert compiled[0] == "error"


_sync_finalizer_calls: list[str] = []


class SyncFinalizedGroup(Group):
    dep = providers.Factory(
        creator=Dep,
        scope=Scope.APP,
        cache=providers.CacheSettings(finalizer=lambda _: _sync_finalizer_calls.append("dep")),
    )


def test_cached_close_sync_runs_finalizer_equivalence() -> None:
    def scenario(interpreted: bool) -> _Outcome:
        _sync_finalizer_calls.clear()
        c = Container(scope=Scope.APP, groups=[SyncFinalizedGroup], validate=False)
        ctx = forced_interpreted() if interpreted else contextlib.nullcontext()
        with ctx:
            c.resolve_provider(SyncFinalizedGroup.dep)
            c.close_sync()
        return ("value", repr(list(_sync_finalizer_calls)))

    compiled, interpreted = _lifecycle_both(scenario)
    assert compiled == interpreted
    assert compiled == ("value", "['dep']")


_lifo_calls: list[str] = []


class LifoGroup(Group):
    dep = providers.Factory(
        creator=Dep, scope=Scope.APP, cache=providers.CacheSettings(finalizer=lambda _: _lifo_calls.append("dep"))
    )
    svc = providers.Factory(
        creator=Service, scope=Scope.APP, cache=providers.CacheSettings(finalizer=lambda _: _lifo_calls.append("svc"))
    )


async def test_cached_finalizer_lifo_order_equivalence() -> None:
    # Two cached providers where svc depends on dep: dep is created (and mark_created) first,
    # so close_async() finalizes in reverse creation order -- svc then dep -- under both paths.
    async def scenario(interpreted: bool) -> _Outcome:
        _lifo_calls.clear()
        c = Container(scope=Scope.APP, groups=[LifoGroup], validate=False)
        ctx = forced_interpreted() if interpreted else contextlib.nullcontext()
        with ctx:
            c.resolve_provider(LifoGroup.svc)
            await c.close_async()
        return ("value", repr(list(_lifo_calls)))

    compiled, interpreted = await _lifecycle_both_async(scenario)
    assert compiled == interpreted
    assert compiled == ("value", "['svc', 'dep']")


_async_finalizer_calls: list[str] = []


async def _async_dep_finalizer(_: Dep) -> None:
    _async_finalizer_calls.append("dep")


class AsyncFinalizerGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP, cache=providers.CacheSettings(finalizer=_async_dep_finalizer))


async def test_cached_close_sync_async_finalizer_raises_equivalence() -> None:
    # close_sync() on a cached provider with an async finalizer raises (FinalizerError wrapping
    # AsyncFinalizerInSyncCloseError) without clearing the cache, per the error's own advice a
    # follow-up close_async() then succeeds and actually runs the finalizer -- both the raise and
    # the recovery are identical under both paths.
    async def scenario(interpreted: bool) -> tuple[str, list[str]]:
        _async_finalizer_calls.clear()
        c = Container(scope=Scope.APP, groups=[AsyncFinalizerGroup], validate=False)
        ctx = forced_interpreted() if interpreted else contextlib.nullcontext()
        with ctx:
            c.resolve_provider(AsyncFinalizerGroup.dep)
            with pytest.raises(exceptions.FinalizerError) as exc_info:
                c.close_sync()
            sync_error = f"{type(exc_info.value).__name__}: {exc_info.value}"
        await c.close_async()
        return sync_error, list(_async_finalizer_calls)

    compiled, interpreted = await scenario(False), await scenario(True)
    assert compiled == interpreted
    assert "AsyncFinalizerInSyncCloseError" in compiled[0]
    assert compiled[1] == ["dep"]


@dataclasses.dataclass(slots=True)
class LifecycleConnection:
    closed: bool = False


async def _close_lifecycle_connection(conn: LifecycleConnection) -> None:
    conn.closed = True


class RequestLifecycleGroup(Group):
    conn = providers.Factory(
        creator=LifecycleConnection,
        scope=Scope.REQUEST,
        cache=providers.CacheSettings(finalizer=_close_lifecycle_connection),
    )


async def test_cached_request_lifecycle_equivalence() -> None:
    # The G7/C4 shape: REQUEST-scoped cached connection, sync creation, async finalizer. Build
    # child, resolve, await close_async() -- closed flips to True identically under both paths.
    async def scenario(interpreted: bool) -> _Outcome:
        app = Container(scope=Scope.APP, groups=[RequestLifecycleGroup], validate=False)
        req = app.build_child_container(scope=Scope.REQUEST)
        ctx = forced_interpreted() if interpreted else contextlib.nullcontext()
        with ctx:
            conn = req.resolve_provider(RequestLifecycleGroup.conn)
            await req.close_async()
        return ("value", repr(conn.closed))

    compiled, interpreted = await _lifecycle_both_async(scenario)
    assert compiled == interpreted
    assert compiled == ("value", "True")


@dataclasses.dataclass(frozen=True, slots=True)
class Unregistered:
    """Never registered in any group below -- stands in for "no provider found"."""


_DEFAULT_UNREGISTERED = Unregistered()


@dataclasses.dataclass(slots=True)
class NullableUser:
    dep: Unregistered | None


@dataclasses.dataclass(slots=True)
class DefaultOmittedUser:
    dep: Unregistered = _DEFAULT_UNREGISTERED


class EdgeGroup(Group):
    nullable_user = providers.Factory(creator=NullableUser, scope=Scope.APP)
    default_user = providers.Factory(creator=DefaultOmittedUser, scope=Scope.APP)


def test_nullable_none_injection_equivalence() -> None:
    # `Unregistered` has no provider; the nullable annotation makes wiring.absent_disposition
    # return NULL, injecting a static `None` kwarg (WiringPlan.static_kwargs, non-pure plan).
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[EdgeGroup], validate=False), EdgeGroup.nullable_user
    )
    assert compiled == interpreted
    assert compiled == ("value", "NullableUser(dep=None)", ())


def test_static_default_omission_equivalence() -> None:
    # `Unregistered` has no provider; the parameter has a creator-side default, so
    # wiring.absent_disposition returns OMIT and the kwarg is left out of resolved_kwargs
    # entirely -- the creator's own default applies.
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[EdgeGroup], validate=False), EdgeGroup.default_user
    )
    assert compiled == interpreted
    assert compiled == ("value", f"DefaultOmittedUser(dep={_DEFAULT_UNREGISTERED!r})", ())


@dataclasses.dataclass(slots=True)
class KwargsMix:
    name: str
    dep: Dep


class KwargsMixGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP)
    mixed = providers.Factory(creator=KwargsMix, scope=Scope.APP, kwargs={"name": "static-value", "dep": dep})


def test_kwargs_static_and_provider_values_equivalence() -> None:
    # A single `kwargs={...}` overlay carrying both a literal value and a provider reference:
    # exercises WiringPlan.build's split of the overlay into static_kwargs vs. provider_kwargs.
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[KwargsMixGroup], validate=False), KwargsMixGroup.mixed
    )
    assert compiled == interpreted
    assert compiled == ("value", "KwargsMix(name='static-value', dep=Dep())", ())


class DirectContextGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)


def test_context_provider_direct_resolve_unset_equivalence() -> None:
    # Direct resolve (not as a dependency) of an unset ContextProvider: falls back to None with
    # a ContextValueNoneWarning. `resolver_for` never compiles a ContextProvider (compile_resolver
    # only handles Factory), so both paths already run the identical `ContextProvider.resolve` body
    # -- this pins that fallback behavior against a future compiled ContextProvider fast path.
    def once(interpreted: bool) -> tuple[_Outcome, list[tuple[str, str]]]:
        c = Container(scope=Scope.APP, groups=[DirectContextGroup], validate=False)
        ctx = forced_interpreted() if interpreted else contextlib.nullcontext()
        with ctx, warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            value = c.resolve_provider(DirectContextGroup.ctx)
        return ("value", repr(value)), [(type(w.message).__name__, str(w.message)) for w in caught]

    compiled, interpreted = once(False), once(True)
    assert compiled == interpreted
    assert compiled[0] == ("value", "None")
    assert [name for name, _msg in compiled[1]] == ["ContextValueNoneWarning"]


def test_closed_container_reuse_warns_equivalence() -> None:
    # Resolving from a container after close_sync(): both paths warn ContainerClosedWarning and
    # self-heal by reopening. `resolve_provider` warns and reopens the entry container itself
    # (both paths); the compiled transient resolver (`_compile_transient_factory`'s inner
    # `resolve`, in resolver_compiler.py) separately guards its navigated *target* container --
    # here entry and target coincide, so both checks must agree without double-warning.
    def scenario(interpreted: bool) -> tuple[_Outcome, list[tuple[str, str]]]:
        c = Container(scope=Scope.APP, groups=[G], validate=False)
        ctx = forced_interpreted() if interpreted else contextlib.nullcontext()
        with ctx:
            c.resolve_provider(G.dep)
            c.close_sync()
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                value = c.resolve_provider(G.dep)
        return ("value", repr(value)), [(type(w.message).__name__, str(w.message)) for w in caught]

    compiled, interpreted = scenario(False), scenario(True)
    assert compiled == interpreted
    assert compiled[0] == ("value", "Dep()")
    assert [name for name, _msg in compiled[1]] == ["ContainerClosedWarning"]


def test_closed_request_child_reaches_app_transient_equivalence() -> None:
    # Entry-container reopen with entry != target: resolve an APP-scoped transient (G.dep) from
    # a CLOSED REQUEST child. The entry container (the REQUEST child) is closed, but the target
    # container (the APP root) never was. `resolve_provider` must warn+reopen the entry itself --
    # the compiled resolver's own `target.closed` guard (resolver_compiler.py) never fires here,
    # since the target is a distinct, still-open container.
    def build() -> Container:
        app_container = Container(scope=Scope.APP, groups=[G], validate=False)
        req = app_container.build_child_container(scope=Scope.REQUEST)
        req.close_sync()
        return req

    compiled, interpreted = _resolve_both(build, G.dep)
    assert compiled == interpreted
    assert compiled[0] == "value"
    assert compiled[2] == ("ContainerClosedWarning",)


def test_target_only_closed_cross_scope_equivalence() -> None:
    # Mirror image of the case above: the entry container (an open REQUEST child) is fine, but
    # the cross-scope TARGET it navigates to (the APP root) is independently closed. Entry-side
    # reopen in `resolve_provider` is a no-op here; the compiled resolver's own `target.closed`
    # guard (resolver_compiler.py) is what fires -- the same distinct check `Factory.resolve`
    # makes via `if target is not container: target._warn_and_reopen_if_closed()`.
    def build() -> Container:
        app_container = Container(scope=Scope.APP, groups=[G], validate=False)
        req = app_container.build_child_container(scope=Scope.REQUEST)
        app_container.close_sync()
        return req

    compiled, interpreted = _resolve_both(build, G.dep)
    assert compiled == interpreted
    assert compiled[0] == "value"
    assert compiled[2] == ("ContainerClosedWarning",)


class SelfRec:
    def __init__(self) -> None:
        raise RecursionError


class SelfRecGroup(Group):
    s = providers.Factory(scope=Scope.APP, creator=SelfRec)


def test_self_recursing_creator_equivalence() -> None:
    # A creator that raises RecursionError directly (no deep Python recursion needed): on a
    # validated (acyclic-static) graph, resolve_provider's RecursionError guard re-raises it
    # unchanged rather than converting it. Exercises the guard on both the compiled dispatch
    # branch and the interpreted-fallback branch (separate except clauses in resolve_provider).
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[SelfRecGroup], validate=True), SelfRecGroup.s
    )
    assert compiled == interpreted


@dataclasses.dataclass(kw_only=True, slots=True)
class CycleA:
    dep: "CycleB"


@dataclasses.dataclass(kw_only=True, slots=True)
class CycleB:
    dep: CycleA


class CycleGroup(Group):
    a = providers.Factory(creator=CycleA, scope=Scope.APP)
    b = providers.Factory(creator=CycleB, scope=Scope.APP)


class DirectAliasGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP)
    alias = providers.Alias(source_type=Dep, bound_type=None)


def test_alias_direct_resolve_equivalence() -> None:
    # Resolving an Alias directly (not as a Factory dependency) exercises the compiled Alias
    # resolver's own entry point, distinct from the fallback-thunk case above.
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[DirectAliasGroup], validate=False), DirectAliasGroup.alias
    )
    assert compiled == interpreted
    assert compiled[0] == "value"


class DanglingAliasDirectGroup(Group):
    alias = providers.Alias(source_type=Dep, bound_type=None)


def test_alias_missing_source_direct_equivalence() -> None:
    # Alias whose source is never registered: error `str()` must match exactly, including the
    # alias's own prepended resolution step (Alias.resolve's try/except wraps this single call).
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[DanglingAliasDirectGroup], validate=False),
        DanglingAliasDirectGroup.alias,
    )
    assert compiled == interpreted
    assert compiled[0] == "error"
    assert "AliasSourceNotRegisteredError" in compiled[1]


class OverrideAliasGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP)
    alias = providers.Alias(source_type=Dep, bound_type=None)
    via_alias = providers.Factory(creator=ViaAlias, scope=Scope.APP, kwargs={"dep": alias})


def test_alias_override_direct_equivalence() -> None:
    # Override applied directly to the Alias: proves the compiled Alias resolver's own
    # override front-guard fires (the compiled dispatch no longer checks overrides centrally).
    def build() -> Container:
        c = Container(scope=Scope.APP, groups=[OverrideAliasGroup], validate=False)
        c.override(OverrideAliasGroup.alias, Dep())
        return c

    compiled, interpreted = _resolve_both(build, OverrideAliasGroup.alias)
    assert compiled == interpreted


def test_alias_override_as_factory_dependency_equivalence() -> None:
    # Same override, but the Alias is reached as a Factory's provider_kwargs dependency
    # (an explicit kwargs={} reference, not auto-wired) -- calls the resolver by reference.
    def build() -> Container:
        c = Container(scope=Scope.APP, groups=[OverrideAliasGroup], validate=False)
        c.override(OverrideAliasGroup.alias, Dep())
        return c

    compiled, interpreted = _resolve_both(build, OverrideAliasGroup.via_alias)
    assert compiled == interpreted


def test_container_provider_direct_resolve_equivalence() -> None:
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[G], validate=False), providers.container_provider
    )
    assert compiled == interpreted
    assert compiled[0] == "value"


class ContainerProviderOverrideDepGroup(Group):
    needs_container = providers.Factory(creator=NeedsContainer, scope=Scope.APP)


def test_container_provider_override_direct_equivalence() -> None:
    def build() -> Container:
        c = Container(scope=Scope.APP, groups=[ContainerProviderOverrideDepGroup], validate=False)
        c.override(providers.container_provider, "mock-container")
        return c

    compiled, interpreted = _resolve_both(build, providers.container_provider)
    assert compiled == interpreted


def test_container_provider_override_as_factory_dependency_equivalence() -> None:
    # ContainerProvider reached as a Factory's auto-wired dependency (NeedsContainer.container:
    # Container), with an override on the provider itself -- the fallback-thunk path.
    def build() -> Container:
        c = Container(scope=Scope.APP, groups=[ContainerProviderOverrideDepGroup], validate=False)
        c.override(providers.container_provider, "mock-container")
        return c

    compiled, interpreted = _resolve_both(build, ContainerProviderOverrideDepGroup.needs_container)
    assert compiled == interpreted


def test_context_provider_direct_resolve_set_equivalence() -> None:
    # Direct resolve of a SET ContextProvider: the compiled resolver delegates to the bound
    # `ContextProvider.resolve`, which must not warn (complements the unset case above).
    now = datetime.datetime.now(tz=datetime.timezone.utc)

    def once(interpreted: bool) -> tuple[_Outcome, tuple[str, ...]]:
        c = Container(scope=Scope.APP, groups=[DirectContextGroup], validate=False, context={datetime.datetime: now})
        ctx = forced_interpreted() if interpreted else contextlib.nullcontext()
        with ctx, warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            value = c.resolve_provider(DirectContextGroup.ctx)
        return ("value", repr(value)), tuple(sorted(type(w.message).__name__ for w in caught))

    compiled, interpreted = once(False), once(True)
    assert compiled == interpreted
    assert compiled == (("value", repr(now)), ())


class ContextOverrideGroup(Group):
    ctx = providers.ContextProvider(scope=Scope.APP, context_type=datetime.datetime)
    needs = providers.Factory(creator=NeedsContext, scope=Scope.APP, kwargs={"arg1": ctx})


def test_context_provider_override_direct_equivalence() -> None:
    # Override applied directly to the ContextProvider: proves the compiled resolver's own
    # front-guard fires (no value is set in the context registry, so this is the ONLY way the
    # provider resolves to a non-None value without warning).
    override_value = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)

    def build() -> Container:
        c = Container(scope=Scope.APP, groups=[ContextOverrideGroup], validate=False)
        c.override(ContextOverrideGroup.ctx, override_value)
        return c

    compiled, interpreted = _resolve_both(build, ContextOverrideGroup.ctx)
    assert compiled == interpreted
    assert compiled == ("value", repr(override_value), ())


def test_context_provider_override_as_factory_dependency_equivalence() -> None:
    # Same override, but the ContextProvider is reached as a Factory's provider_kwargs dependency
    # (explicit kwargs={} reference -- not the auto-wired context_kwargs bucket that bypasses the
    # compiled resolver entirely) -- calls the resolver by reference.
    override_value = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)

    def build() -> Container:
        c = Container(scope=Scope.APP, groups=[ContextOverrideGroup], validate=False)
        c.override(ContextOverrideGroup.ctx, override_value)
        return c

    compiled, interpreted = _resolve_both(build, ContextOverrideGroup.needs)
    assert compiled == interpreted


class _UnknownProvider(providers.AbstractProvider[object]):
    def resolve(self, container: Container) -> object:  # noqa: ARG002 (unused; body below is unreachable)
        return object()  # pragma: no cover - never reached (compile_resolver raises before resolve is called)


def test_compile_resolver_raises_for_unhandled_provider_type() -> None:
    # Every real provider type compiles; an unknown subclass hits the final explicit raise --
    # the bridge fallthrough it replaces is gone, so this is the only way this branch is reached.
    c = Container(scope=Scope.APP, validate=False)
    provider = _UnknownProvider(scope=Scope.APP, bound_type=None)
    with pytest.raises(TypeError, match="no compiled resolver for provider type _UnknownProvider"):
        c.resolve_provider(provider)


def test_genuine_cycle_str_equivalence() -> None:
    """Genuine 2-node cycle A->B->A: compiled vs interpreted CircularDependencyError str must match.

    Reconciled by two changes, together making the two paths emit an identical error:

    (a) Canonical rotation in `build_cycle_error` (modern_di/dependency_graph.py): any cycle ring
    is rotated to start at its minimum-`provider_id` node before rendering, so the "Circular
    dependency detected: ..." block is byte-identical regardless of which node the catching frame
    seeded the walk from (and deterministic across interpreted runs).

    (b) `CircularDependencyError.prepend_step` is a no-op (modern_di/exceptions.py): the canonical
    cycle is self-contained -- every provider in the loop is already named -- so neither path
    accumulates an outer "Cannot resolve dependency chain: ..." breadcrumb. Without this, the
    interpreted path (which unwinds through every intermediate `resolve_provider` frame, each
    prepending a step) would grow a breadcrumb the compiled path (single top-level conversion)
    never gets.
    """
    original_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_SHALLOW_RECURSION_LIMIT)
    try:
        compiled, interpreted = _resolve_both(
            lambda: Container(scope=Scope.APP, groups=[CycleGroup], validate=False), CycleGroup.a
        )
    # coverage.py suspends trace calls for a few frames while a RecursionError unwinds; lines that
    # run immediately after can be flakily under-reported in a full-suite run (100% in isolation).
    # Same known CPython/coverage.py interaction that test_runtime_cycle_guard.py marks no-cover.
    finally:  # pragma: no cover
        sys.setrecursionlimit(original_limit)
    assert compiled[0] == interpreted[0] == "error"  # pragma: no cover
    assert compiled == interpreted  # pragma: no cover


# --- Positional creator fast path (guarded) ------------------------------------------------------
#
# `_positional_names` is the compile-time predicate that decides whether a Factory's creator can be
# called positionally (`creator(v0, v1, ...)`) instead of `creator(**kwargs)`. Eligible only when the
# whole parsed signature is provider deps, in order, with no static/context/omitted/keyword-only
# params. These tests pin the predicate's verdict AND the runtime equivalence of both call styles.


def _eligibility(container: Container, provider: "providers.Factory[typing.Any]") -> "tuple[str, ...] | None":
    """Compute `_positional_names` for `provider` against `container`'s live registry."""
    plan = container.providers_registry.plan_for(provider, provider._parsed_kwargs, provider._kwargs)  # noqa: SLF001
    return _positional_names(provider, plan)


def test_positional_zero_arg_eligible() -> None:
    # A 0-arg pure provider is positional-eligible: `creator()` with an empty arg list.
    container = Container(scope=Scope.APP, groups=[G], validate=False)
    assert _eligibility(container, G.leaf) == ()
    compiled, interpreted = _resolve_both(lambda: Container(scope=Scope.APP, groups=[G], validate=False), G.leaf)
    assert compiled == interpreted
    assert compiled == ("value", "Leaf()", ())


def test_positional_one_arg_eligible() -> None:
    # A 1-arg pure provider (Service(dep: Dep), positional-or-keyword) is eligible.
    container = Container(scope=Scope.APP, groups=[G], validate=False)
    assert _eligibility(container, G.svc) == ("dep",)
    compiled, interpreted = _resolve_both(lambda: Container(scope=Scope.APP, groups=[G], validate=False), G.svc)
    assert compiled == interpreted
    assert compiled == ("value", "Service(dep=Dep())", ())


@dataclasses.dataclass(slots=True)
class Pos3:
    a: W0
    b: W1
    c: W2


class Pos3Group(Group):
    w0 = providers.Factory(creator=W0, scope=Scope.APP)
    w1 = providers.Factory(creator=W1, scope=Scope.APP)
    w2 = providers.Factory(creator=W2, scope=Scope.APP)
    thing = providers.Factory(creator=Pos3, scope=Scope.APP)


def test_positional_three_arg_chain_eligible() -> None:
    # Three positional-or-keyword provider deps, in signature order: eligible for the positional call.
    container = Container(scope=Scope.APP, groups=[Pos3Group], validate=False)
    assert _eligibility(container, Pos3Group.thing) == ("a", "b", "c")
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[Pos3Group], validate=False), Pos3Group.thing
    )
    assert compiled == interpreted
    assert compiled == ("value", "Pos3(a=W0(), b=W1(), c=W2())", ())


_UNUSED_DEP = Dep()


@dataclasses.dataclass(slots=True)
class MiddleGap:
    a: Dep
    b: Unregistered = _DEFAULT_UNREGISTERED  # no provider + default -> OMITted (a middle gap)
    c: Dep = _UNUSED_DEP  # has a provider -> resolved live; the default is never used


class MiddleGapGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP)
    thing = providers.Factory(creator=MiddleGap, scope=Scope.APP)


def test_positional_middle_gap_ineligible() -> None:
    # The NEGATIVE case a naive positional call would break: `b` is omitted (default, no provider),
    # so provider_kwargs is (a, c) -- a non-contiguous subset of the (a, b, c) signature. It MUST
    # stay on the kwargs path, and still resolve correctly on both paths.
    container = Container(scope=Scope.APP, groups=[MiddleGapGroup], validate=False)
    assert _eligibility(container, MiddleGapGroup.thing) is None
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[MiddleGapGroup], validate=False), MiddleGapGroup.thing
    )
    assert compiled == interpreted
    assert compiled == ("value", f"MiddleGap(a=Dep(), b={_DEFAULT_UNREGISTERED!r}, c=Dep())", ())


@dataclasses.dataclass(kw_only=True, slots=True)
class KwOnlyDep:
    dep: Dep


class KwOnlyGroup(Group):
    dep = providers.Factory(creator=Dep, scope=Scope.APP)
    thing = providers.Factory(creator=KwOnlyDep, scope=Scope.APP)


def test_positional_keyword_only_ineligible() -> None:
    # A keyword-only provider dep cannot be passed positionally: stays on the kwargs path even
    # though every param IS a provider dep in order. Still resolves identically on both paths.
    container = Container(scope=Scope.APP, groups=[KwOnlyGroup], validate=False)
    assert _eligibility(container, KwOnlyGroup.thing) is None
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[KwOnlyGroup], validate=False), KwOnlyGroup.thing
    )
    assert compiled == interpreted
    assert compiled == ("value", "KwOnlyDep(dep=Dep())", ())


@dataclasses.dataclass(slots=True)
class PosNeedsReq:
    req: ReqOnly


class PosDepStepErrorGroup(Group):
    req = providers.Factory(creator=ReqOnly, scope=Scope.REQUEST)
    thing = providers.Factory(creator=PosNeedsReq, scope=Scope.APP)


def test_positional_dependency_step_error_equivalence() -> None:
    # A positional-eligible transient whose REQUEST-scoped dependency is unreachable from the APP
    # container: the ScopeNotInitializedError is raised while resolving the positional args, so the
    # resolve_positional breadcrumb (_STEP_ERRORS/prepend_step) must fire, matching the kwargs path.
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[PosDepStepErrorGroup], validate=False), PosDepStepErrorGroup.thing
    )
    assert compiled == interpreted
    assert compiled[0] == "error"


class CachedPosDepStepErrorGroup(Group):
    req = providers.Factory(creator=ReqOnly, scope=Scope.REQUEST)
    thing = providers.Factory(creator=PosNeedsReq, scope=Scope.APP, cache=True)


def test_cached_positional_dependency_step_error_equivalence() -> None:
    # The cached counterpart: exercises the cold-miss build_args breadcrumb on the positional path.
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[CachedPosDepStepErrorGroup], validate=False),
        CachedPosDepStepErrorGroup.thing,
    )
    assert compiled == interpreted
    assert compiled[0] == "error"


@dataclasses.dataclass(slots=True)
class OneArgResult:
    required: Dep


def _needs_one_arg(required: Dep) -> OneArgResult:
    return OneArgResult(required=required)


class PositionalBindingErrorGroup(Group):
    # skip_creator_parsing -> parsed_kwargs is empty -> positional-eligible with 0 args, but the
    # creator needs one. `creator()` raises a binding TypeError with no inner frame (tb_next None),
    # so the positional path's CreatorCallError wrap must fire, matching the kwargs path.
    thing = providers.Factory(
        creator=_needs_one_arg, scope=Scope.APP, skip_creator_parsing=True, bound_type=OneArgResult
    )


def test_positional_binding_typeerror_equivalence() -> None:
    assert _needs_one_arg(Dep()) == OneArgResult(required=Dep())  # exercise the creator body for coverage
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[PositionalBindingErrorGroup], validate=False),
        PositionalBindingErrorGroup.thing,
    )
    assert compiled == interpreted
    assert compiled[0] == "error"
    assert "CreatorCallError" in compiled[1]


class CachedPositionalBindingErrorGroup(Group):
    thing = providers.Factory(
        creator=_needs_one_arg, scope=Scope.APP, skip_creator_parsing=True, bound_type=OneArgResult, cache=True
    )


def test_cached_positional_binding_typeerror_equivalence() -> None:
    # The cached counterpart: exercises the create_positional CreatorCallError wrap on the cold-miss
    # path.
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[CachedPositionalBindingErrorGroup], validate=False),
        CachedPositionalBindingErrorGroup.thing,
    )
    assert compiled == interpreted
    assert compiled[0] == "error"
    assert "CreatorCallError" in compiled[1]


class CachedBodyTypeErrorGroup(Group):
    # Cached + positional (skip_creator_parsing -> 0 args) creator whose body raises TypeError
    # (inner frame present): create_positional must let it propagate UNCHANGED, not wrap it.
    thing = providers.Factory(
        creator=BodyTypeError, scope=Scope.APP, bound_type=BodyTypeError, skip_creator_parsing=True, cache=True
    )


def test_cached_positional_body_typeerror_propagates_equivalence() -> None:
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[CachedBodyTypeErrorGroup], validate=False),
        CachedBodyTypeErrorGroup.thing,
    )
    assert compiled == interpreted
    assert compiled[0] == "error"
    assert compiled[1].startswith("TypeError:")  # propagated unchanged, not wrapped in CreatorCallError


def test_kwargs_path_target_only_closed_cross_scope_equivalence() -> None:
    # The mirror of test_target_only_closed_cross_scope_equivalence for an INELIGIBLE (keyword-only)
    # provider: the cross-scope TARGET (the APP root) is independently closed, so the *kwargs-path*
    # resolver's own target.closed guard fires -- distinct from the positional resolver's guard,
    # keeping both closures' closed-target branch covered.
    def build() -> Container:
        app_container = Container(scope=Scope.APP, groups=[KwOnlyGroup], validate=False)
        req = app_container.build_child_container(scope=Scope.REQUEST)
        app_container.close_sync()
        return req

    compiled, interpreted = _resolve_both(build, KwOnlyGroup.thing)
    assert compiled == interpreted
    assert compiled[0] == "value"
    assert compiled[2] == ("ContainerClosedWarning",)


class KwOnlyBodyTypeError:
    def __init__(self, *, dep: Dep) -> None:  # noqa: ARG002 - unused; the body raises before it is read
        len(5)  # ty: ignore[invalid-argument-type]  # TypeError inside the body (inner frame present)


class KwOnlyBodyTypeErrorGroup(Group):
    # An INELIGIBLE (keyword-only dep) creator whose body raises TypeError: forces the kwargs-path
    # closure and its tb_next guard, which must let the TypeError propagate UNCHANGED (not wrap it),
    # mirroring the positional path's body-TypeError case.
    dep = providers.Factory(creator=Dep, scope=Scope.APP)
    thing = providers.Factory(creator=KwOnlyBodyTypeError, scope=Scope.APP)


def test_kwargs_path_body_typeerror_propagates_equivalence() -> None:
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[KwOnlyBodyTypeErrorGroup], validate=False),
        KwOnlyBodyTypeErrorGroup.thing,
    )
    assert compiled == interpreted
    assert compiled[0] == "error"
    assert compiled[1].startswith("TypeError:")  # propagated unchanged, not wrapped in CreatorCallError


@dataclasses.dataclass(slots=True)
class PosOnlyResult:
    prefix: str
    dep: Dep


def pos_only_creator(prefix: str = "P", /, dep: Dep = None) -> PosOnlyResult:  # ty: ignore[invalid-parameter-default]
    return PosOnlyResult(prefix=prefix, dep=dep)


class PosOnlyGroup(Group):
    # `prefix` is positional-only WITH a default: _parse_parameter drops it from _parsed_kwargs
    # entirely (types_parser.py), so `_parsed_kwargs` holds only `dep` -- names == ("dep",), a
    # clean-looking prefix of provider_kwargs. Without the positional-only guard in
    # _positional_names, this would be misjudged eligible and `creator(dep_instance)` would bind
    # dep_instance to `prefix`, silently swallowing the "P" default. Must stay on the kwargs path.
    dep = providers.Factory(creator=Dep, scope=Scope.APP)
    thing = providers.Factory(creator=pos_only_creator, scope=Scope.APP)


def test_positional_only_with_default_ineligible() -> None:
    container = Container(scope=Scope.APP, groups=[PosOnlyGroup], validate=False)
    assert _eligibility(container, PosOnlyGroup.thing) is None
    compiled, interpreted = _resolve_both(
        lambda: Container(scope=Scope.APP, groups=[PosOnlyGroup], validate=False), PosOnlyGroup.thing
    )
    assert compiled == interpreted
    assert compiled == ("value", "PosOnlyResult(prefix='P', dep=Dep())", ())
