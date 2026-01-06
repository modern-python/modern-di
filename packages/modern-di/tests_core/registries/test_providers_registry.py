import pytest
from modern_di import providers
from modern_di.registries.providers_registry import ProvidersRegistry


def test_providers_registry_find_provider_not_found() -> None:
    providers_registry = ProvidersRegistry()
    assert providers_registry.find_provider() is None


def test_providers_registry_add_provider_duplicates() -> None:
    str_factory = providers.Factory(creator=lambda: "string", bound_type=str)

    providers_registry = ProvidersRegistry()
    providers_registry.add_providers(str_factory=str_factory)

    with (
        pytest.warns(RuntimeWarning, match="Provider is duplicated by name"),
        pytest.warns(RuntimeWarning, match="Provider is duplicated by type"),
    ):
        providers_registry.add_providers(str_factory=str_factory)
