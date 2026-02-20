import abc
from modern_di import Container, Group, Scope, providers


def test_container_provider_direct_resolving() -> None:
    app_container = Container()
    assert app_container.resolve(Container) is app_container

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    assert request_container.resolve_provider(providers.container_provider) is request_container


def test_container_provider_sub_dependency() -> None:
    def creator(di_container: Container) -> Scope:
        return di_container.scope

    class MyGroup(Group):
        factory = providers.Factory(scope=Scope.REQUEST, creator=creator)

    app_container = Container(groups=[MyGroup])
    request_container = app_container.build_child_container(scope=Scope.REQUEST)

    instance = request_container.resolve(Scope)
    assert instance == Scope.REQUEST


def test_container_provider_with_qualifier_direct_resolving() -> None:
    class SomeDep(abc.ABC):
        pass

    class SomeDepA(SomeDep):
        pass

    class SomeDepB(SomeDep):
        pass

    class SomeGroup(Group):
        dep = providers.Factory(creator=SomeDepA, bound_type=SomeDep)
        another_dep = providers.Factory(creator=SomeDepB, bound_type=SomeDep, qualifier="another")

    container = Container(groups=[SomeGroup])

    assert isinstance(container.resolve(SomeDep), SomeDepA)

    assert isinstance(container.resolve(SomeDep, qualifier="another"), SomeDepB)
