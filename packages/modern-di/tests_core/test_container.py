import copy

import pytest
from modern_di import AsyncContainer, Scope, SyncContainer, providers


def test_container_not_opened() -> None:
    container = SyncContainer()
    with pytest.raises(RuntimeError, match="Enter the context of APP scope"):
        container.resolve_provider(providers.ContainerProvider(Scope.APP))


def test_container_prevent_copy() -> None:
    container = SyncContainer()
    container_deepcopy = copy.deepcopy(container)
    container_copy = copy.copy(container)
    assert container_deepcopy is container_copy is container


def test_container_scope_skipped() -> None:
    app_factory = providers.Factory(Scope.APP, lambda: "test")
    with SyncContainer(scope=Scope.REQUEST) as container, pytest.raises(RuntimeError, match="Scope APP is skipped"):
        container.resolve_provider(app_factory)


async def test_container_build_child_async() -> None:
    async with (
        AsyncContainer() as app_container,
        app_container.build_child_container(scope=Scope.REQUEST) as request_container,
    ):
        assert request_container.scope == Scope.REQUEST
        assert app_container.scope == Scope.APP


def test_container_build_child_sync() -> None:
    with (
        SyncContainer() as app_container,
        app_container.build_child_container(scope=Scope.REQUEST) as request_container,
    ):
        assert request_container.scope == Scope.REQUEST
        assert app_container.scope == Scope.APP


def test_container_scope_limit_reached() -> None:
    with (
        SyncContainer(scope=Scope.STEP) as app_container,
        pytest.raises(RuntimeError, match="Max scope is reached, STEP"),
    ):
        app_container.build_child_container()


def test_container_build_child_wrong_scope() -> None:
    with (
        SyncContainer() as app_container,
        pytest.raises(RuntimeError, match="Scope of child container must be more than current scope"),
    ):
        app_container.build_child_container(scope=Scope.APP)


async def test_async_container_resolve_missing_provider() -> None:
    async with AsyncContainer() as app_container:
        with pytest.raises(RuntimeError, match="Provider is not found"):
            assert await app_container.resolve(str) is None


def test_sync_container_resolve_missing_provider() -> None:
    with SyncContainer() as app_container:
        assert app_container.resolve(str) is None
