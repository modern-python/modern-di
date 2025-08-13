import copy

import pytest
from modern_di import Container, Scope, providers


def test_container_not_opened() -> None:
    container = Container(scope=Scope.APP)
    with pytest.raises(RuntimeError, match="Enter the context of APP scope"):
        container.fetch_provider_state("some_id")


def test_container_prevent_copy() -> None:
    container = Container(scope=Scope.APP)
    container_deepcopy = copy.deepcopy(container)
    container_copy = copy.copy(container)
    assert container_deepcopy is container_copy is container


def test_container_scope_skipped() -> None:
    app_factory = providers.Factory(Scope.APP, lambda: "test")
    with Container(scope=Scope.REQUEST) as container, pytest.raises(RuntimeError, match="Scope APP is skipped"):
        app_factory.sync_resolve(container)


async def test_container_build_child_async() -> None:
    async with (
        Container(scope=Scope.APP) as app_container,
        app_container.build_child_container(scope=Scope.REQUEST) as request_container,
    ):
        assert request_container.scope == Scope.REQUEST
        assert app_container.scope == Scope.APP


def test_container_build_child_sync() -> None:
    with (
        Container(scope=Scope.APP) as app_container,
        app_container.build_child_container(scope=Scope.REQUEST) as request_container,
    ):
        assert request_container.scope == Scope.REQUEST
        assert app_container.scope == Scope.APP


def test_container_scope_limit_reached() -> None:
    with Container(scope=Scope.STEP) as app_container, pytest.raises(RuntimeError, match="Max scope is reached, STEP"):
        app_container.build_child_container()


async def test_container_build_child_wrong_scope() -> None:
    with (
        Container(scope=Scope.APP) as app_container,
        pytest.raises(RuntimeError, match="Scope of child container must be more than current scope"),
    ):
        app_container.build_child_container(scope=Scope.APP)
