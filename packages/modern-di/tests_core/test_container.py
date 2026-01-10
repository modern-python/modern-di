import copy

import pytest
from modern_di import Container, Scope, providers


def test_container_prevent_copy() -> None:
    container = Container()
    container_deepcopy = copy.deepcopy(container)
    container_copy = copy.copy(container)
    assert container_deepcopy is container_copy is container


def test_container_scope_skipped() -> None:
    app_factory = providers.Factory(creator=lambda: "test")
    container = Container(scope=Scope.REQUEST)
    with pytest.raises(RuntimeError, match="Scope APP is skipped"):
        container.resolve_provider(app_factory)


def test_container_build_child() -> None:
    app_container = Container()
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    assert request_container.scope == Scope.REQUEST
    assert app_container.scope == Scope.APP


def test_container_scope_limit_reached() -> None:
    step_container = Container(scope=Scope.STEP)
    with pytest.raises(RuntimeError, match="Max scope is reached, STEP"):
        step_container.build_child_container()


def test_container_build_child_wrong_scope() -> None:
    app_container = Container()
    with pytest.raises(RuntimeError, match="Scope of child container must be more than current scope"):
        app_container.build_child_container(scope=Scope.APP)


def test_container_resolve_missing_provider() -> None:
    app_container = Container()
    with pytest.raises(RuntimeError, match="Provider is not found"):
        assert app_container.resolve(str) is None
