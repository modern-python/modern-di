import sys
import threading

import pytest

from modern_di import providers
from modern_di.exceptions import DuplicateProviderTypeError
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.scope import Scope


def test_providers_registry_find_provider_not_found() -> None:
    providers_registry = ProvidersRegistry()
    assert providers_registry.find_provider(str) is None


def test_providers_registry_add_provider_duplicates() -> None:
    str_factory = providers.Factory(creator=lambda: "string", bound_type=str)

    providers_registry = ProvidersRegistry()
    providers_registry.add_providers(str_factory)

    with pytest.raises(DuplicateProviderTypeError, match="Provider is duplicated by type <class 'str'>") as exc:
        providers_registry.add_providers(str_factory)
    assert exc.value.provider_type is str


def test_providers_registry_register_duplicate_raises() -> None:
    str_factory = providers.Factory(creator=lambda: "string", bound_type=str)

    providers_registry = ProvidersRegistry()
    providers_registry.register(str, str_factory)

    with pytest.raises(DuplicateProviderTypeError, match="Provider is duplicated by type <class 'str'>") as exc:
        providers_registry.register(str, str_factory)
    assert exc.value.provider_type is str


class _RaceBase: ...


def test_iteration_is_safe_while_another_thread_registers() -> None:
    registry = ProvidersRegistry()
    race_types = [type(f"_Race{i}", (_RaceBase,), {}) for i in range(2000)]
    for one_type in race_types[:1000]:
        registry.register(
            one_type,
            providers.Factory(scope=Scope.APP, creator=one_type, skip_creator_parsing=True, bound_type=one_type),
        )

    errors_seen: list[BaseException] = []
    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:

        def writer() -> None:
            for one_type in race_types[1000:]:
                registry.register(
                    one_type,
                    providers.Factory(
                        scope=Scope.APP, creator=one_type, skip_creator_parsing=True, bound_type=one_type
                    ),
                )

        def reader() -> None:
            try:
                for _ in range(50):
                    list(iter(registry))
                    registry.build_suggestions(_RaceBase)
            except BaseException as e:  # noqa: BLE001  # pragma: no cover
                errors_seen.append(e)  # pragma: no cover

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old_interval)

    assert errors_seen == []
