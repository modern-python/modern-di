from modern_di import Container, providers


provider1 = providers.Factory(creator=lambda: "str1", cache_settings=providers.CacheSettings(), bound_type=str)
provider2 = providers.Factory(creator=lambda: "str2", cache_settings=providers.CacheSettings(), bound_type=str)
sequence = providers.List(provider1, provider2)


def test_list_async() -> None:
    app_container = Container()
    sequence1 = app_container.resolve_provider(sequence)
    sequence2 = app_container.resolve_provider(sequence)
    instance1 = app_container.resolve_provider(provider1)
    instance2 = app_container.resolve_provider(provider2)
    assert sequence1 == sequence2 == [instance1, instance2]
