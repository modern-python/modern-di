import dataclasses

import pytest
from modern_di import Container, Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


class MyGroup(Group):
    app_factory = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "original"})
    request_factory = providers.Factory(scope=Scope.REQUEST, creator=DependentCreator)


def test_app_factory() -> None:
    app_container = Container()
    instance1 = app_container.resolve_provider(MyGroup.app_factory)
    instance2 = app_container.resolve_provider(MyGroup.app_factory)
    assert instance1 is not instance2


def test_app_factory_with_registry() -> None:
    app_container = Container(groups=[MyGroup])
    instance1 = app_container.resolve(dependency_type=SimpleCreator)
    instance2: SimpleCreator = app_container.resolve(dependency_name="app_factory")
    assert isinstance(instance1, SimpleCreator)
    assert isinstance(instance2, SimpleCreator)
    assert instance1 is not instance2


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


def test_factory_overridden_app_scope() -> None:
    app_container = Container()
    instance1 = app_container.resolve_provider(MyGroup.app_factory)

    app_container.override(MyGroup.app_factory, SimpleCreator(dep1="override"))

    instance2 = app_container.resolve_provider(MyGroup.app_factory)
    instance3 = app_container.resolve_provider(MyGroup.app_factory)
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
    instance1 = request_container.resolve_provider(MyGroup.request_factory)
    instance2 = request_container.resolve_provider(MyGroup.request_factory)
    assert instance1 is instance2
    assert instance2.dep1.dep1 == instance1.dep1.dep1 == "override"

    request_container.reset_override(MyGroup.request_factory)

    instance3 = request_container.resolve_provider(MyGroup.request_factory)

    assert instance3 is not instance1


def test_factory_overridden_after_request_scope_closed() -> None:
    app_container = Container(groups=[MyGroup])
    app_container.override(MyGroup.request_factory, DependentCreator(dep1=SimpleCreator(dep1="override")))

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance1 = request_container.resolve_provider(MyGroup.request_factory)

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance2 = request_container.resolve_provider(MyGroup.request_factory)

    assert instance1 is instance2
    assert instance2.dep1.dep1 == instance1.dep1.dep1 == "override"

    app_container.reset_override()
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    instance3 = request_container.resolve_provider(MyGroup.request_factory)
    assert instance3.dep1.dep1 != instance1.dep1.dep1


def test_factory_scope_is_not_initialized() -> None:
    app_container = Container(groups=[MyGroup])
    with pytest.raises(RuntimeError, match="Scope REQUEST is not initialize"):
        app_container.resolve_provider(MyGroup.request_factory)
