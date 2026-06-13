import dataclasses
import re
import unittest.mock
import warnings

import pytest

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


def test_factory_repr() -> None:
    provider = providers.Factory(creator=str, scope=Scope.APP)
    assert repr(provider) == "Factory(creator=<class 'str'>, scope=<Scope.APP: 1>, cached=False)"


def test_factory_repr_cached() -> None:
    provider = providers.Factory(creator=str, scope=Scope.APP, cache_settings=providers.CacheSettings())
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
        cache_settings=providers.CacheSettings(finalizer=lambda _: _flaky_events.append("dep")),
    )
    svc = providers.Factory(
        scope=Scope.APP,
        creator=_FlakySvc,
        cache_settings=providers.CacheSettings(finalizer=lambda _: _flaky_events.append("svc")),
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
        cache_settings=providers.CacheSettings(),
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
