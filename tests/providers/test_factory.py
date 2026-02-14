import dataclasses
import re

import pytest

from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


@dataclasses.dataclass(kw_only=True, slots=True)
class AnotherCreator:
    dep1: SimpleCreator
    di_container: Container


def func_with_union(dep1: SimpleCreator | int) -> str:
    return str(dep1)


def func_with_broken_annotation(dep1: "SomeWrongClass") -> None: ...  # type: ignore[name-defined]  # noqa: F821


class MyGroup(Group):
    app_factory = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "original"})
    app_factory_unresolvable = providers.Factory(creator=SimpleCreator, bound_type=None)
    app_factory_skip_creator_parsing = providers.Factory(creator=SimpleCreator, skip_creator_parsing=True)
    func_with_union_factory = providers.Factory(creator=func_with_union, bound_type=None)
    func_with_broken_annotation = providers.Factory(creator=func_with_broken_annotation, bound_type=None)
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
    with pytest.raises(RuntimeError, match="Argument dep1 cannot be resolved, type=<class 'str'"):
        app_container.resolve_provider(MyGroup.app_factory_unresolvable)


def test_func_with_union_factory() -> None:
    app_container = Container(groups=[MyGroup])
    instance1 = app_container.resolve_provider(MyGroup.func_with_union_factory)
    assert instance1


def test_func_with_broken_annotation() -> None:
    app_container = Container(groups=[MyGroup])
    with pytest.raises(RuntimeError, match="Argument dep1 cannot be resolved, type=None"):
        app_container.resolve_provider(MyGroup.func_with_broken_annotation)


def test_request_factory() -> None:
    app_container = Container(groups=[MyGroup])
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance1 = request_container.resolve_provider(MyGroup.request_factory)
    instance2 = request_container.resolve_provider(MyGroup.request_factory)
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
    with pytest.raises(RuntimeError, match="Scope REQUEST is not initialize"):
        app_container.resolve_provider(MyGroup.request_factory)


def test_factory_self_reference() -> None:
    def second_creator(first_factory: str) -> str:
        return f"{first_factory} two"

    first_factory = providers.Factory(creator=lambda: "one")
    second_factory = providers.Factory(creator=second_creator, kwargs={"first_factory": first_factory})

    app_container = Container()
    app_container.providers_registry.add_providers(first_factory, second_factory)

    assert app_container.resolve_provider(second_factory) == "one two"
