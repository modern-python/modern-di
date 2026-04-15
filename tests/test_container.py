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
    with pytest.raises(RuntimeError, match=r"Provider of scope APP is skipped in the chain of containers."):
        container.resolve_provider(app_factory)


def test_container_build_child() -> None:
    app_container = Container()
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    assert request_container.scope == Scope.REQUEST
    assert app_container.scope == Scope.APP


def test_container_scope_limit_reached() -> None:
    step_container = Container(scope=Scope.STEP)
    with pytest.raises(RuntimeError, match=r"Max scope of STEP is reached."):
        step_container.build_child_container()


def test_container_build_child_wrong_scope() -> None:
    app_container = Container()
    with pytest.raises(RuntimeError, match="Scope of child container cannot be"):
        app_container.build_child_container(scope=Scope.APP)


def test_container_resolve_missing_provider() -> None:
    app_container = Container()
    with pytest.raises(RuntimeError, match=r"Provider of type <class 'str'> is not registered in providers registry."):
        assert app_container.resolve(str) is None


def test_container_sync_context_manager() -> None:
    with Container() as container:
        assert container.scope == Scope.APP

    with container.build_child_container(scope=Scope.REQUEST) as request_container:
        assert request_container.scope == Scope.REQUEST


async def test_container_async_context_manager() -> None:
    async with Container() as container:
        assert container.scope == Scope.APP

    async with container.build_child_container(scope=Scope.REQUEST) as request_container:
        assert request_container.scope == Scope.REQUEST


def test_container_repr() -> None:
    container = Container()
    assert repr(container) == "Container(scope=<Scope.APP: 1>, providers=1, cached=0)"
