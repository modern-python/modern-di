import dataclasses

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


class MyGroup(Group):
    app_factory = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "original"})
    request_factory = providers.Factory(scope=Scope.REQUEST, creator=DependentCreator)
    request_factory_with_di_container = providers.Factory(scope=Scope.REQUEST, creator=AnotherCreator)


def test_app_factory() -> None:
    app_container = Container(groups=[MyGroup])
    instance1 = app_container.resolve_provider(MyGroup.app_factory)
    instance2 = app_container.resolve(dependency_type=SimpleCreator)
    instance3: SimpleCreator = app_container.resolve(dependency_name="app_factory")
    assert isinstance(instance1, SimpleCreator)
    assert isinstance(instance2, SimpleCreator)
    assert isinstance(instance3, SimpleCreator)
    assert instance1 is not instance2
    assert instance1 is not instance3
    assert instance2 is not instance3


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

    app_container.override(
        dependency_name="app_factory",
        dependency_type=SimpleCreator,
        new_provider=providers.Object(obj=SimpleCreator(dep1="override")),
    )

    instance2 = app_container.resolve(SimpleCreator)
    instance3 = app_container.resolve(SimpleCreator)
    assert instance1 is not instance2
    assert instance2 is instance3
    assert instance2.dep1 != instance1.dep1

    app_container.reset_override(dependency_name="app_factory", dependency_type=SimpleCreator)

    instance4 = app_container.resolve_provider(MyGroup.app_factory)

    assert instance4.dep1 == instance1.dep1

    assert instance3 is not instance4


def test_factory_overridden_request_scope() -> None:
    app_container = Container(groups=[MyGroup])
    app_container.override(
        dependency_name="request_factory",
        dependency_type=DependentCreator,
        new_provider=providers.Object(obj=DependentCreator(dep1=SimpleCreator(dep1="override"))),
    )

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance1 = request_container.resolve(DependentCreator)
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
