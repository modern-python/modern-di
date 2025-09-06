import dataclasses

import pytest
from modern_di import AsyncContainer, Scope, SyncContainer, providers
from modern_di.registries.providers_registry import ProvidersRegistry


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
request_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)


async def test_app_factory() -> None:
    async with AsyncContainer() as app_container:
        instance1 = await app_container.resolve_provider(app_factory)
        instance2 = await app_container.resolve_provider(app_factory)
        assert instance1 is not instance2

    with SyncContainer() as app_container:
        instance3 = app_container.resolve_provider(app_factory)
        instance4 = app_container.resolve_provider(app_factory)
        assert instance3 is not instance4
        assert instance1 is not instance3


async def test_app_factory_with_registry_async_container() -> None:
    providers_registry = ProvidersRegistry()
    providers_registry.add_providers(app_factory=app_factory)
    async with AsyncContainer(providers_registry=providers_registry) as app_container:
        instance1 = await app_container.resolve(dependency_type=SimpleCreator)
        instance2 = await app_container.resolve(dependency_name="app_factory")  # type: ignore[func-returns-value]
        assert isinstance(instance1, SimpleCreator)
        assert isinstance(instance2, SimpleCreator)
        assert instance1 is not instance2


def test_app_factory_with_registry_sync_container() -> None:
    providers_registry = ProvidersRegistry()
    providers_registry.add_providers(app_factory=app_factory)
    with SyncContainer(providers_registry=providers_registry) as app_container:
        instance1 = app_container.resolve(dependency_type=SimpleCreator)
        instance2 = app_container.resolve(dependency_name="app_factory")
        assert isinstance(instance1, SimpleCreator)
        assert isinstance(instance2, SimpleCreator)
        assert instance1 is not instance2


def test_request_factory() -> None:
    with SyncContainer() as app_container:
        with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
            instance1 = request_container.resolve_provider(request_factory)
            instance2 = request_container.resolve_provider(request_factory)
            assert instance1 is not instance2

        with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
            instance3 = request_container.resolve_provider(request_factory)
            instance4 = request_container.resolve_provider(request_factory)
            assert instance3 is not instance4

        assert instance1 is not instance3


def test_app_factory_in_request_scope() -> None:
    with SyncContainer() as app_container:
        with app_container.build_child_container():
            instance1 = app_container.resolve_provider(app_factory)

        with app_container.build_child_container():
            instance2 = app_container.resolve_provider(app_factory)

        assert instance1 is not instance2


async def test_factory_overridden_app_scope() -> None:
    async with AsyncContainer() as app_container:
        instance1 = await app_container.resolve_provider(app_factory)

        app_container.override(app_factory, SimpleCreator(dep1="override"))

        instance2 = await app_container.resolve_provider(app_factory)
        instance3 = await app_container.resolve_provider(app_factory)
        assert instance1 is not instance2
        assert instance2 is instance3
        assert instance2.dep1 != instance1.dep1

        app_container.reset_override(app_factory)

        instance4 = await app_container.resolve_provider(app_factory)

        assert instance4.dep1 == instance1.dep1

        assert instance3 is not instance4


async def test_factory_overridden_request_scope() -> None:
    async with AsyncContainer() as app_container:
        app_container.override(request_factory, DependentCreator(dep1=SimpleCreator(dep1="override")))

        async with app_container.build_child_container(scope=Scope.REQUEST) as request_container:
            instance1 = await request_container.resolve_provider(request_factory)
            instance2 = await request_container.resolve_provider(request_factory)
            assert instance1 is instance2
            assert instance2.dep1.dep1 == instance1.dep1.dep1 == "override"

            request_container.reset_override(request_factory)

            instance3 = await request_container.resolve_provider(request_factory)

            assert instance3 is not instance1


async def test_factory_wrong_dependency_scope() -> None:
    def some_factory(_: SimpleCreator) -> None: ...

    request_factory_ = providers.Factory(Scope.REQUEST, SimpleCreator, dep1="original")
    with pytest.raises(RuntimeError, match="Scope of dependency is REQUEST and current scope is APP"):
        providers.Singleton(Scope.APP, some_factory, request_factory_.cast)


async def test_factory_scope_is_not_initialized() -> None:
    with SyncContainer() as app_container, pytest.raises(RuntimeError, match="Scope REQUEST is not initialize"):
        app_container.resolve_provider(request_factory)
