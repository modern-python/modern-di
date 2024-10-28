import pytest

from modern_di import BaseGraph, Container, Scope, resolvers
from tests.creators import create_async_resource, create_sync_resource


async_resource = resolvers.Resource(Scope.APP, create_async_resource)
sync_resource = resolvers.Resource(Scope.APP, create_sync_resource)


async def test_graph_async_resolve_creators() -> None:
    class DIGraph(BaseGraph):
        async_resource = async_resource
        sync_resource = sync_resource

    async with Container(scope=Scope.APP) as app_container:
        await DIGraph.async_resolve_creators(app_container)

        assert len(app_container._resolver_states) == 2  # noqa: SLF001, PLR2004
    assert len(app_container._resolver_states) == 0  # noqa: SLF001


def test_graph_sync_resolve_creators() -> None:
    class DIGraph(BaseGraph):
        sync_resource = sync_resource

    with Container(scope=Scope.APP) as app_container:
        DIGraph.sync_resolve_creators(app_container)

        assert len(app_container._resolver_states) == 1  # noqa: SLF001
    assert len(app_container._resolver_states) == 0  # noqa: SLF001


def test_graph_cannot_be_instantiated() -> None:
    class DIGraph(BaseGraph):
        sync_resource = sync_resource

    with pytest.raises(RuntimeError, match="DIGraph cannot not be instantiated"):
        DIGraph()
