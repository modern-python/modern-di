import pytest
from modern_di import Container, Scope, providers


provider1 = providers.Singleton[str](Scope.APP, lambda: "str1")
provider2 = providers.Singleton[str](Scope.APP, lambda: "str2")
mapping = providers.Dict(Scope.APP, dep1=provider1, dep2=provider2)


def test_dict_async() -> None:
    app_container = Container()
    mapping1 = app_container.resolve_provider(mapping)
    mapping2 = app_container.resolve_provider(mapping)
    instance1 = app_container.resolve_provider(provider1)
    instance2 = app_container.resolve_provider(provider2)
    assert mapping1 == mapping2 == {"dep1": instance1, "dep2": instance2}


def test_dict_wrong_scope() -> None:
    request_factory_ = providers.Factory(Scope.REQUEST, lambda: "")
    with pytest.raises(RuntimeError, match="Scope of dep1 is REQUEST and current scope is APP"):
        providers.Dict(Scope.APP, dep1=request_factory_)
