from modern_di import Container, providers


provider1 = providers.Factory(creator=lambda: "str1")
provider2 = providers.Factory(creator=lambda: "str2")
mapping = providers.Dict(dep1=provider1, dep2=provider2)


def test_dict_async() -> None:
    app_container = Container()
    mapping1 = app_container.resolve_provider(mapping)
    mapping2 = app_container.resolve_provider(mapping)
    instance1 = app_container.resolve_provider(provider1)
    instance2 = app_container.resolve_provider(provider2)
    assert mapping1 == mapping2 == {"dep1": instance1, "dep2": instance2}
