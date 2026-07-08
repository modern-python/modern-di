import contextlib
import dataclasses
import functools
import inspect
import re
import unittest.mock
import warnings

import pytest

import modern_di.wiring as wiring_mod
from modern_di import Container, Group, Scope, exceptions, providers
from modern_di.exceptions import ArgumentResolutionError, ScopeNotInitializedError, UnknownFactoryKwargError


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class DependentCreator:
    dep1: SimpleCreator


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class AnotherCreator:
    dep1: SimpleCreator
    di_container: Container


def func_with_union(dep1: SimpleCreator | int) -> str:
    return str(dep1)


def func_with_broken_annotation(dep1: "SomeWrongClass") -> None: ...  # ty: ignore[unresolved-reference]  # noqa: F821


class MyGroup(Group):
    app_factory = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "original"})
    app_factory_unresolvable = providers.Factory(creator=SimpleCreator, bound_type=None)
    app_factory_skip_creator_parsing = providers.Factory(
        creator=SimpleCreator, skip_creator_parsing=True, bound_type=None
    )
    func_with_union_factory = providers.Factory(creator=func_with_union, bound_type=None)
    request_factory = providers.Factory(scope=Scope.REQUEST, creator=DependentCreator)
    request_factory_with_di_container = providers.Factory(scope=Scope.REQUEST, creator=AnotherCreator)


def test_app_factory() -> None:
    app_container = Container(groups=[MyGroup])
    instance1 = app_container.resolve_provider(MyGroup.app_factory)
    instance2 = app_container.resolve(dependency_type=SimpleCreator)
    assert isinstance(instance1, SimpleCreator)
    assert isinstance(instance2, SimpleCreator)
    assert instance1 is not instance2


def test_app_factory_skip_creator_parsing() -> None:
    app_container = Container(groups=[MyGroup])
    with pytest.raises(
        exceptions.CreatorCallError,
        match=re.escape("SimpleCreator.__init__() missing 1 required keyword-only argument: 'dep1'"),
    ):
        app_container.resolve_provider(MyGroup.app_factory_skip_creator_parsing)


def test_app_factory_unresolvable() -> None:
    app_container = Container(groups=[MyGroup])
    with pytest.raises(ArgumentResolutionError, match="Argument dep1 of type <class 'str'> cannot be resolved") as exc:
        app_container.resolve_provider(MyGroup.app_factory_unresolvable)
    assert exc.value.arg_name == "dep1"
    assert exc.value.arg_type is str


def test_func_with_union_factory() -> None:
    app_container = Container(groups=[MyGroup])
    instance1 = app_container.resolve_provider(MyGroup.func_with_union_factory)
    assert instance1 == str(SimpleCreator(dep1="original"))


def test_func_with_broken_annotation() -> None:
    with pytest.warns(UserWarning, match="Failed to resolve type hints"):
        factory = providers.Factory(creator=func_with_broken_annotation, bound_type=None)

    app_container = Container()
    app_container.providers_registry.add_providers(factory)
    with pytest.raises(ArgumentResolutionError, match="has no usable type annotation"):
        app_container.resolve_provider(factory)


def test_request_factory() -> None:
    app_container = Container(groups=[MyGroup])
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    request_container.resolve_provider(MyGroup.request_factory)
    instance1 = request_container.resolve_provider(MyGroup.request_factory)
    instance2 = request_container.resolve_provider(MyGroup.request_factory)
    request_container.resolve_provider(MyGroup.request_factory)
    assert instance1 is not instance2

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance3 = request_container.resolve_provider(MyGroup.request_factory)
    instance4 = request_container.resolve_provider(MyGroup.request_factory)
    assert instance3 is not instance4

    assert instance1 is not instance3


def test_request_factory_with_di_container() -> None:
    app_container = Container(groups=[MyGroup])
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance1 = request_container.resolve_provider(MyGroup.request_factory_with_di_container)
    instance2 = request_container.resolve_provider(MyGroup.request_factory_with_di_container)
    assert instance1 is not instance2
    assert isinstance(instance1.di_container, Container)
    assert instance1.di_container.scope == Scope.REQUEST
    assert instance1.di_container is instance2.di_container

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance3 = request_container.resolve_provider(MyGroup.request_factory_with_di_container)
    instance4 = request_container.resolve_provider(MyGroup.request_factory_with_di_container)
    assert instance3 is not instance4

    assert instance1 is not instance3


def test_factory_overridden_app_scope() -> None:
    app_container = Container(groups=[MyGroup])
    instance1 = app_container.resolve_provider(MyGroup.app_factory)

    app_container.override(MyGroup.app_factory, SimpleCreator(dep1="override"))

    instance2 = app_container.resolve(SimpleCreator)
    instance3 = app_container.resolve(SimpleCreator)
    assert instance1 is not instance2
    assert instance2 is instance3
    assert instance2.dep1 != instance1.dep1

    app_container.reset_override(MyGroup.app_factory)

    instance4 = app_container.resolve_provider(MyGroup.app_factory)

    assert instance4.dep1 == instance1.dep1

    assert instance3 is not instance4


def test_factory_overridden_request_scope() -> None:
    app_container = Container(groups=[MyGroup])
    app_container.override(MyGroup.request_factory, DependentCreator(dep1=SimpleCreator(dep1="override")))

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance1 = request_container.resolve(DependentCreator)
    request_container.close_sync()

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance2 = request_container.resolve(DependentCreator)
    assert instance1 is instance2
    assert instance2.dep1.dep1 == instance1.dep1.dep1 == "override"

    request_container.reset_override()

    instance3 = request_container.resolve(DependentCreator)

    assert instance3 is not instance1


def test_override_bypasses_scope_check_from_shallower_container() -> None:
    # Documented intentional: an override is returned before the scope check, so a
    # deeper-scoped provider can be resolved from a shallower container — see
    # architecture/testing-and-overrides.md "Scope behaviour under overrides".
    app_container = Container(groups=[MyGroup])
    with pytest.raises(ScopeNotInitializedError):
        app_container.resolve_provider(MyGroup.request_factory)

    override = DependentCreator(dep1=SimpleCreator(dep1="override"))
    app_container.override(MyGroup.request_factory, override)
    assert app_container.resolve_provider(MyGroup.request_factory) is override


def test_factory_scope_is_not_initialized() -> None:
    app_container = Container(groups=[MyGroup])
    with pytest.raises(
        ScopeNotInitializedError,
        match=r"Provider of scope REQUEST cannot be resolved in container of scope APP.",
    ) as exc:
        app_container.resolve_provider(MyGroup.request_factory)
    assert exc.value.provider_scope == Scope.REQUEST
    assert exc.value.container_scope == Scope.APP


def test_factory_self_reference() -> None:
    def second_creator(first_factory: str) -> str:
        return f"{first_factory} two"

    first_factory = providers.Factory(creator=lambda: "one")
    second_factory = providers.Factory(creator=second_creator, kwargs={"first_factory": first_factory})

    app_container = Container()
    app_container.providers_registry.add_providers(first_factory, second_factory)

    assert app_container.resolve_provider(second_factory) == "one two"


def test_factory_self_reference_in_union_falls_through_to_default() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class SelfRef:
        x: int = 1

    def make(x: int | SelfRef = 1) -> SelfRef:
        return SelfRef(x=x if isinstance(x, int) else x.x)

    factory = providers.Factory(creator=make)
    app_container = Container()
    app_container.providers_registry.add_providers(factory)

    result = app_container.resolve(SelfRef)
    assert isinstance(result, SelfRef)
    assert result.x == 1


def test_factory_self_reference_by_type_falls_through_to_default() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class SelfRefByType:
        nested: "SelfRefByType | None" = None

    def make(nested: SelfRefByType = SelfRefByType()) -> SelfRefByType:  # noqa: B008
        return nested

    factory = providers.Factory(creator=make)
    app_container = Container()
    app_container.providers_registry.add_providers(factory)

    # `nested` is typed as the factory's own bound type: it must not wire to itself,
    # and with no other provider it falls through to the creator default.
    result = app_container.resolve(SelfRefByType)
    assert isinstance(result, SelfRefByType)
    assert result.nested is None


def test_factory_repr() -> None:
    provider = providers.Factory(creator=str, scope=Scope.APP)
    assert repr(provider) == "Factory(creator=<class 'str'>, scope=<Scope.APP: 1>, cached=False)"


def test_factory_repr_cached() -> None:
    provider = providers.Factory(creator=str, scope=Scope.APP, cache=True)
    assert repr(provider) == "Factory(creator=<class 'str'>, scope=<Scope.APP: 1>, cached=True)"


def test_factory_skip_creator_parsing_without_bound_type_warns() -> None:
    with pytest.warns(UserWarning, match="skip_creator_parsing=True without an explicit bound_type"):
        providers.Factory(creator=str, skip_creator_parsing=True)


def test_factory_skip_creator_parsing_with_bound_type_no_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        providers.Factory(creator=str, skip_creator_parsing=True, bound_type=str)


def test_factory_rejects_unknown_kwarg_at_construction() -> None:
    with pytest.raises(UnknownFactoryKwargError) as exc:
        providers.Factory(creator=lambda a=1: a, kwargs={"a": 1, "nonexistent": "oops"})
    assert "nonexistent" in str(exc.value)
    assert "a" in exc.value.known_keys
    assert "nonexistent" in exc.value.unknown_keys


def test_factory_unknown_kwarg_suggests_close_match() -> None:
    with pytest.raises(UnknownFactoryKwargError) as exc:
        providers.Factory(
            creator=lambda connection_string="default": connection_string, kwargs={"connetion_string": "x"}
        )
    assert "connection_string" in str(exc.value)


def test_factory_kwarg_validation_skips_when_signature_unavailable() -> None:
    # When inspect.signature raises (e.g. for some C-implemented callables),
    # the validator silently skips rather than crashing.
    with unittest.mock.patch("inspect.signature", side_effect=ValueError):
        providers.Factory(creator=lambda x=1: x, kwargs={"anything": 1})


def test_factory_allows_extra_kwargs_when_creator_accepts_var_keyword() -> None:
    def make(**kwargs: object) -> dict[str, object]:
        return kwargs

    factory = providers.Factory(creator=make, kwargs={"anything": 1, "extra": 2})
    container = Container()
    container.providers_registry.add_providers(factory)
    result = container.resolve(dict)
    assert result == {"anything": 1, "extra": 2}


def test_factory_default_value_compared_with_is_not_eq() -> None:
    class SomeUnregisteredType:
        pass

    def make(x: SomeUnregisteredType = unittest.mock.ANY) -> str:
        return repr(x)

    factory = providers.Factory(creator=make)
    container = Container()
    container.providers_registry.add_providers(factory)
    result = container.resolve(str)
    assert result == repr(unittest.mock.ANY)


def _unannotated_creator(x):  # noqa: ANN001, ANN202
    return x


class _UnannotatedGroup(Group):
    svc = providers.Factory(creator=_unannotated_creator, bound_type=object, scope=Scope.APP)


def test_unannotated_param_error_explains_missing_annotation() -> None:
    sentinel = object()
    assert _unannotated_creator(sentinel) is sentinel  # exercise body for coverage
    container = Container(scope=Scope.APP, groups=[_UnannotatedGroup])
    with pytest.raises(ArgumentResolutionError, match="has no usable type annotation"):
        container.resolve(object)


class _UnionDep1: ...


class _UnionDep2: ...


def _union_creator(x: _UnionDep1 | _UnionDep2) -> str:
    return str(x)


class _UnionGroup(Group):
    svc = providers.Factory(creator=_union_creator, scope=Scope.APP)


def test_union_param_error_names_the_union_members() -> None:
    dep = _UnionDep1()
    assert _union_creator(dep) == str(dep)  # exercise body for coverage
    container = Container(scope=Scope.APP, groups=[_UnionGroup])
    with pytest.raises(ArgumentResolutionError, match=r"_UnionDep1 \| _UnionDep2"):
        container.resolve(str)


# Q-10 — static kwargs beat a type-matched provider


class _PrecedenceDep:
    def __init__(self, label: str = "from-provider") -> None:
        self.label = label


class _PrecedenceSvc:
    def __init__(self, dep: _PrecedenceDep) -> None:
        self.dep = dep


_static_dep = _PrecedenceDep(label="from-kwargs")


class _PrecedenceGroup(Group):
    dep = providers.Factory(scope=Scope.APP, creator=_PrecedenceDep)
    svc = providers.Factory(scope=Scope.APP, creator=_PrecedenceSvc, kwargs={"dep": _static_dep})


def test_static_kwargs_win_over_type_matched_provider() -> None:
    container = Container(scope=Scope.APP, groups=[_PrecedenceGroup])
    svc = container.resolve(_PrecedenceSvc)
    assert svc.dep is _static_dep
    assert svc.dep.label == "from-kwargs"


# Q-11 — creator raising mid-creation: nothing cached, retry succeeds, deps finalized LIFO


_flaky_state = {"raised": False}
_flaky_events: list[str] = []


class _FlakyDep: ...


class _FlakySvc:
    def __init__(self, dep: _FlakyDep) -> None:
        if not _flaky_state["raised"]:
            _flaky_state["raised"] = True
            msg = "boom"
            raise RuntimeError(msg)
        self.dep = dep


class _FlakyGroup(Group):
    dep = providers.Factory(
        scope=Scope.APP,
        creator=_FlakyDep,
        cache=providers.CacheSettings(finalizer=lambda _: _flaky_events.append("dep")),
    )
    svc = providers.Factory(
        scope=Scope.APP,
        creator=_FlakySvc,
        cache=providers.CacheSettings(finalizer=lambda _: _flaky_events.append("svc")),
    )


def test_creator_raising_mid_creation_caches_nothing_and_retry_succeeds() -> None:
    _flaky_state["raised"] = False
    _flaky_events.clear()
    container = Container(scope=Scope.APP, groups=[_FlakyGroup])
    with pytest.raises(RuntimeError, match="boom"):
        container.resolve(_FlakySvc)
    expected_cached_after_failure = 1  # only the dep cached; failed svc not cached
    assert container.cache_registry.cached_count() == expected_cached_after_failure
    retried = container.resolve(_FlakySvc)
    assert isinstance(retried, _FlakySvc)
    container.close_sync()
    assert _flaky_events == ["svc", "dep"]  # LIFO (B-7): svc created after dep, finalized first


def test_provider_instances_have_no_dict() -> None:
    factory: providers.Factory[object] = providers.Factory(creator=object, scope=Scope.APP)
    assert not hasattr(factory, "__dict__")
    with pytest.raises(AttributeError):
        factory.some_unexpected_attr = 1


def test_compile_kwargs_is_memoized_across_resolves() -> None:
    # Pins the compile-once invariant: kwargs compilation (type lookups + partitioning) runs
    # exactly once per provider per container, not on every resolve. A regression that moved it
    # back onto the per-resolve path would leave correctness tests green but silently slow.
    class _MemoGroup(Group):
        leaf = providers.Factory(scope=Scope.APP, creator=SimpleCreator, kwargs={"dep1": "x"})
        svc = providers.Factory(scope=Scope.APP, creator=DependentCreator)

    container = Container(groups=[_MemoGroup])
    real_build = wiring_mod.WiringPlan.build
    with unittest.mock.patch.object(wiring_mod.WiringPlan, "build", autospec=True, side_effect=real_build) as build_spy:
        container.resolve(DependentCreator)
        container.resolve(DependentCreator)
    # svc + leaf each build their plan once on the first resolve; the second reuses the memo (else this is 4).
    expected_build_calls = 2
    assert build_spy.call_count == expected_build_calls


# Q-1 / G-3 — optional (X | None) params inject None when no provider is registered


class _OptionalDep: ...


class _OtherDep: ...


class _NeedsOptionalSingle:
    def __init__(self, dep: _OptionalDep | None) -> None:
        self.dep = dep


class _NeedsOptionalUnion:
    def __init__(self, dep: "_OptionalDep | _OtherDep | None") -> None:
        self.dep = dep


def test_optional_param_injects_none_when_no_provider() -> None:
    factory: providers.Factory[_NeedsOptionalSingle] = providers.Factory(creator=_NeedsOptionalSingle, scope=Scope.APP)
    container = Container(scope=Scope.APP)
    container.providers_registry.register(_NeedsOptionalSingle, factory)
    obj = container.resolve(_NeedsOptionalSingle)
    assert obj.dep is None


def test_optional_param_uses_provider_when_present() -> None:
    dep_factory: providers.Factory[_OptionalDep] = providers.Factory(creator=_OptionalDep, scope=Scope.APP)
    factory: providers.Factory[_NeedsOptionalSingle] = providers.Factory(creator=_NeedsOptionalSingle, scope=Scope.APP)
    container = Container(scope=Scope.APP)
    container.providers_registry.register(_OptionalDep, dep_factory)
    container.providers_registry.register(_NeedsOptionalSingle, factory)
    obj = container.resolve(_NeedsOptionalSingle)
    assert isinstance(obj.dep, _OptionalDep)


def test_optional_multi_member_union_injects_none_when_no_provider() -> None:
    factory: providers.Factory[_NeedsOptionalUnion] = providers.Factory(creator=_NeedsOptionalUnion, scope=Scope.APP)
    container = Container(scope=Scope.APP)
    container.providers_registry.register(_NeedsOptionalUnion, factory)
    obj = container.resolve(_NeedsOptionalUnion)
    assert obj.dep is None


def test_validate_does_not_flag_optional_param_without_provider() -> None:
    factory: providers.Factory[_NeedsOptionalSingle] = providers.Factory(creator=_NeedsOptionalSingle, scope=Scope.APP)
    container = Container(scope=Scope.APP)
    container.providers_registry.register(_NeedsOptionalSingle, factory)
    container.validate()  # must not raise


# G-3 branch (b) — a ContextProvider is FOUND for the type, value UNSET, param nullable, no default → None


class _OptionalCtx: ...


class _NeedsOptionalCtx:
    def __init__(self, ctx: _OptionalCtx | None) -> None:
        self.ctx = ctx


def test_optional_param_backed_by_unset_context_provider_injects_none() -> None:
    ctx_provider: providers.ContextProvider[_OptionalCtx] = providers.ContextProvider(
        scope=Scope.APP, context_type=_OptionalCtx
    )
    factory: providers.Factory[_NeedsOptionalCtx] = providers.Factory(creator=_NeedsOptionalCtx, scope=Scope.APP)
    container = Container(scope=Scope.APP)
    container.providers_registry.register(_OptionalCtx, ctx_provider)
    container.providers_registry.register(_NeedsOptionalCtx, factory)
    obj = container.resolve(_NeedsOptionalCtx)
    assert obj.ctx is None


# X-2 — creator-call TypeError (missing required args under skip_creator_parsing) wrapped in DI error


def _needs_two_args(a: int, b: int) -> int:
    return a + b


def test_skip_creator_parsing_missing_args_raises_di_error() -> None:
    factory: providers.Factory[int] = providers.Factory(
        creator=_needs_two_args, bound_type=int, skip_creator_parsing=True, kwargs={"a": 1}
    )
    container = Container(scope=Scope.APP)
    container.providers_registry.register(int, factory)
    with pytest.raises(exceptions.CreatorCallError) as exc_info:
        container.resolve(int)
    assert "_needs_two_args" in str(exc_info.value)
    assert isinstance(exc_info.value, exceptions.ResolutionError)
    assert _needs_two_args(1, 2) == 1 + 2  # exercise helper body


def test_skip_creator_parsing_missing_args_cached_raises_di_error() -> None:
    factory: providers.Factory[int] = providers.Factory(
        creator=_needs_two_args,
        bound_type=int,
        skip_creator_parsing=True,
        kwargs={"a": 1},
        cache=True,
    )
    container = Container(scope=Scope.APP)
    container.providers_registry.register(int, factory)
    with pytest.raises(exceptions.CreatorCallError) as exc_info:
        container.resolve(int)
    assert "_needs_two_args" in str(exc_info.value)
    assert isinstance(exc_info.value, exceptions.ResolutionError)


class _InternalTypeErrorService:
    def __init__(self) -> None:
        len(5)  # ty: ignore[invalid-argument-type]  # internal bug, not a wiring problem


def test_internal_typeerror_from_creator_body_is_not_wrapped() -> None:
    # A TypeError raised inside the creator body must propagate as the creator's own error,
    # not be misattributed as a CreatorCallError wiring problem (it ran, then failed internally).
    factory: providers.Factory[_InternalTypeErrorService] = providers.Factory(
        creator=_InternalTypeErrorService, bound_type=_InternalTypeErrorService, skip_creator_parsing=True
    )
    container = Container(scope=Scope.APP)
    container.providers_registry.register(_InternalTypeErrorService, factory)
    with pytest.raises(TypeError) as exc_info:
        container.resolve(_InternalTypeErrorService)
    assert not isinstance(exc_info.value, exceptions.CreatorCallError)
    assert "len()" in str(exc_info.value)


# Regression: memoized plan must not compound breadcrumbs across repeated resolves


class _UnregisteredDep:
    pass


class _NeedsUnregistered:
    def __init__(self, dep: _UnregisteredDep) -> None:
        self.dep = dep  # pragma: no cover


def test_repeated_failing_resolve_breadcrumb_does_not_compound() -> None:
    """Resolving an unwireable provider twice must produce identical error strings.

    Before the fix, ``prepend_step`` mutated the memoized exception in place so the
    dependency path grew on every call (e.g. "NeedsUnregistered → NeedsUnregistered →
    …" on the third resolve).
    """
    factory: providers.Factory[_NeedsUnregistered] = providers.Factory(creator=_NeedsUnregistered, scope=Scope.APP)
    container = Container(scope=Scope.APP)
    container.providers_registry.register(_NeedsUnregistered, factory)

    def _grab() -> str:
        try:
            container.resolve(_NeedsUnregistered)
        except exceptions.ResolutionError as exc:
            return str(exc)
        return ""  # pragma: no cover

    first = _grab()
    second = _grab()
    third = _grab()
    assert first == second == third, f"breadcrumb compounded: {first!r} != {second!r}"


def test_nested_then_direct_resolve_does_not_leak_parent_breadcrumb() -> None:
    """After a parent's failing resolve, a direct resolve of the leaf must not include the parent's step.

    Before the fix, the leaf's memoized exception was mutated by the parent's
    ``prepend_step``, so subsequent direct resolves of the leaf incorrectly showed the
    parent in the chain.
    """

    class _MissingDep:
        pass

    class _Leaf2:
        def __init__(self, dep: _MissingDep) -> None:
            self.dep = dep  # pragma: no cover

    class _Parent2:
        def __init__(self, leaf: _Leaf2) -> None:
            self.leaf = leaf  # pragma: no cover

    leaf2: providers.Factory[_Leaf2] = providers.Factory(creator=_Leaf2, scope=Scope.APP)
    parent2: providers.Factory[_Parent2] = providers.Factory(creator=_Parent2, scope=Scope.APP)
    c2 = Container(scope=Scope.APP)
    c2.providers_registry.register(_Leaf2, leaf2)
    c2.providers_registry.register(_Parent2, parent2)

    # Resolve parent — propagates through leaf → parent step prepended
    with contextlib.suppress(exceptions.ResolutionError):
        c2.resolve(_Parent2)

    # Now resolve leaf directly — its error must NOT contain Parent2's breadcrumb
    try:
        c2.resolve(_Leaf2)
    except exceptions.ResolutionError as exc:
        leaf_err = str(exc)
        assert "Parent2" not in leaf_err, f"Parent2 leaked into leaf error: {leaf_err!r}"
    else:
        pytest.fail("Expected ResolutionError when resolving _Leaf2 directly")  # pragma: no cover


def test_cache_true_returns_same_instance() -> None:
    class G(Group):
        f = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "x"}, cache=True)

    container = Container(groups=[G])
    assert container.resolve_provider(G.f) is container.resolve_provider(G.f)
    assert isinstance(G.f.cache_settings, providers.CacheSettings)


def test_cache_absent_returns_fresh_instances() -> None:
    class G(Group):
        f = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "x"})

    container = Container(groups=[G])
    assert container.resolve_provider(G.f) is not container.resolve_provider(G.f)
    assert G.f.cache_settings is None


@pytest.mark.parametrize("cache_value", [False, None])
def test_cache_falsy_disables_caching(cache_value: bool | None) -> None:
    class G(Group):
        f = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "x"}, cache=cache_value)

    container = Container(groups=[G])
    assert container.resolve_provider(G.f) is not container.resolve_provider(G.f)
    assert G.f.cache_settings is None


def test_cache_accepts_cache_settings_and_finalizes() -> None:
    cleaned: list[object] = []

    class G(Group):
        f = providers.Factory(creator=dict, cache=providers.CacheSettings(finalizer=cleaned.append))

    container = Container(groups=[G])
    instance = container.resolve_provider(G.f)
    assert container.resolve_provider(G.f) is instance
    container.close_sync()
    assert cleaned == [instance]


def test_cache_settings_is_deprecated_but_functional() -> None:
    with pytest.warns(DeprecationWarning, match="cache_settings"):
        provider = providers.Factory(
            creator=SimpleCreator, kwargs={"dep1": "x"}, cache_settings=providers.CacheSettings()
        )
    container = Container()
    assert container.resolve_provider(provider) is container.resolve_provider(provider)


def test_cache_settings_none_emits_no_deprecation_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        provider = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "x"}, cache_settings=None)
    assert provider.cache_settings is None


def test_cache_and_cache_settings_together_raise() -> None:
    with pytest.raises(TypeError, match="pass only `cache`"):
        providers.Factory(
            creator=SimpleCreator, kwargs={"dep1": "x"}, cache=True, cache_settings=providers.CacheSettings()
        )


def test_repr_reports_cached_for_cache_true() -> None:
    provider = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "x"}, cache=True)
    assert "cached=True" in repr(provider)


def test_factory_accepts_positional_creator() -> None:
    class G(Group):
        factory = providers.Factory(SimpleCreator, kwargs={"dep1": "positional"})

    container = Container(groups=[G], validate=True)
    instance = container.resolve(SimpleCreator)
    assert instance.dep1 == "positional"


def test_factory_rejects_creator_passed_twice() -> None:
    with pytest.raises(TypeError, match="creator"):
        providers.Factory(SimpleCreator, creator=SimpleCreator)  # ty: ignore[parameter-already-assigned]


def _definition_site_func() -> str:
    return "x"


def test_definition_site_function_creator() -> None:
    assert _definition_site_func() == "x"  # exercise body for coverage
    factory = providers.Factory(_definition_site_func, bound_type=None)
    expected = f"{_definition_site_func.__module__}:{_definition_site_func.__code__.co_firstlineno}"
    assert factory.definition_site == expected


def test_definition_site_class_creator() -> None:
    factory = providers.Factory(SimpleCreator, kwargs={"dep1": "x"})
    lineno = inspect.getsourcelines(SimpleCreator)[1]
    assert factory.definition_site == f"{SimpleCreator.__module__}:{lineno}"


def test_definition_site_c_callable_is_none() -> None:
    factory = providers.Factory(dict, bound_type=None, skip_creator_parsing=True)
    assert factory.definition_site is None


def test_definition_site_partial_is_none() -> None:
    factory = providers.Factory(functools.partial(SimpleCreator, dep1="x"), bound_type=None, skip_creator_parsing=True)
    assert factory.definition_site is None


def test_definition_site_memoized(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = providers.Factory(SimpleCreator, kwargs={"dep1": "x"})
    first = factory.definition_site
    assert first is not None

    def _boom(_obj: object) -> tuple[list[str], int]:
        raise AssertionError  # pragma: no cover — must not run; memoization short-circuits before inspect

    monkeypatch.setattr("modern_di.providers.factory.inspect.getsourcelines", _boom)
    assert factory.definition_site == first  # cached; inspect not called again


class _NoModuleCreator:
    def __call__(self) -> str:
        return "x"


def test_definition_site_creator_without_module_is_none() -> None:
    # A creator whose __module__ can't be determined (e.g. a dynamically built callable):
    # _compute_definition_site must bail out before touching __code__/inspect.
    creator = _NoModuleCreator()
    assert creator() == "x"  # exercise body for coverage
    creator.__module__ = None  # ty: ignore[invalid-assignment]
    factory = providers.Factory(creator, bound_type=str, skip_creator_parsing=True)
    assert factory.definition_site is None
