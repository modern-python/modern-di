from modern_di import Container, Scope, providers


container_provider = providers.ContainerProvider(Scope.APP)


def test_container_provider() -> None:
    app_container = Container()
    instance1 = app_container.resolve_provider(container_provider)
    instance2 = app_container.resolve_provider(container_provider)
    assert instance1 is instance2 is app_container
