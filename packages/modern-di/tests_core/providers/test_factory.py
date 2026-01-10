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


def test_factory_scope_is_not_initialized() -> None:
    app_container = Container(groups=[MyGroup])
    with pytest.raises(RuntimeError, match="Scope REQUEST is not initialize"):
        app_container.resolve_provider(MyGroup.request_factory)
