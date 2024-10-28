import enum

import pytest

from modern_di import Container, Scope


def test_container_wrong_init() -> None:
    with pytest.raises(RuntimeError, match="Only first scope can be used without parent_container"):
        Container(scope=Scope.REQUEST)


def test_container_not_opened() -> None:
    container = Container(scope=Scope.APP)
    with pytest.raises(RuntimeError, match="Enter the context first"):
        container.fetch_resolver_state("some_id")


async def test_container_build_child_async() -> None:
    async with Container(scope=Scope.APP) as app_container, app_container.build_child_container() as request_container:
        assert request_container.scope == Scope.REQUEST
        assert app_container.scope == Scope.APP


def test_container_build_child_sync() -> None:
    with Container(scope=Scope.APP) as app_container, app_container.build_child_container() as request_container:
        assert request_container.scope == Scope.REQUEST
        assert app_container.scope == Scope.APP


def test_container_scope_limit_reached() -> None:
    class CustomScope(enum.IntEnum):
        APP = 1
        REQUEST = 2

    with Container(scope=CustomScope.APP) as app_container, app_container.build_child_container() as request_container:
        assert request_container.scope == CustomScope.REQUEST
        assert app_container.scope == CustomScope.APP

        with pytest.raises(RuntimeError, match="Max scope is reached, REQUEST"):
            request_container.build_child_container()
