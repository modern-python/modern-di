from modern_di import Container, Group, Scope, providers


def test_container_provider_direct_resolving() -> None:
    app_container = Container()
    app_container.open()
    assert app_container.resolve(Container) is app_container

    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    request_container.open()
    assert request_container.resolve_provider(providers.container_provider) is request_container


def test_container_provider_sub_dependency() -> None:
    def creator(di_container: Container) -> Scope:
        return Scope(di_container.scope)

    class MyGroup(Group):
        factory = providers.Factory(scope=Scope.REQUEST, creator=creator)

    app_container = Container(groups=[MyGroup])
    app_container.open()
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    request_container.open()

    instance = request_container.resolve(Scope)
    assert instance == Scope.REQUEST


def test_container_provider_override_direct() -> None:
    # Overriding the container provider and resolving it directly exercises the compiled
    # container-provider resolver's own override front-guard (dispatch no longer checks centrally).
    app_container = Container()
    app_container.open()
    app_container.override(providers.container_provider, "mock-container")
    assert app_container.resolve_provider(providers.container_provider) == "mock-container"
