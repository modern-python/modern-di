import pytest
from modern_di import Container, Scope, providers


provider1 = providers.Singleton[str](Scope.APP, lambda: "str1")
provider2 = providers.Singleton[str](Scope.APP, lambda: "str2")
sequence = providers.List(Scope.APP, provider1, provider2)


def test_list_async() -> None:
    app_container = Container()
    sequence1 = app_container.resolve_provider(sequence)
    sequence2 = app_container.resolve_provider(sequence)
    instance1 = app_container.resolve_provider(provider1)
    instance2 = app_container.resolve_provider(provider2)
    assert sequence1 == sequence2 == [instance1, instance2]


def test_list_wrong_scope() -> None:
    request_factory_ = providers.Factory(Scope.REQUEST, lambda: "")
    with pytest.raises(RuntimeError, match="Scope of dependency is REQUEST and current scope is APP"):
        providers.List(Scope.APP, request_factory_)
