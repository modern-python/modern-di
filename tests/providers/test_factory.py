import dataclasses
import re
import unittest.mock
import warnings

import pytest

from modern_di import Container, Group, Scope, providers
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
        TypeError, match=re.escape("SimpleCreator.__init__() missing 1 required keyword-only argument: 'dep1'")
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
    with pytest.raises(ArgumentResolutionError, match="Argument dep1 of type None cannot be resolved"):
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
