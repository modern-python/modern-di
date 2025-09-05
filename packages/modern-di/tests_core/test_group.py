import pytest
from modern_di import Group, Scope, providers

from tests_core.creators import create_sync_resource


sync_resource = providers.Resource(Scope.APP, create_sync_resource)


def test_group_cannot_be_instantiated() -> None:
    class DIGraph(Group):
        sync_resource = sync_resource

    with pytest.raises(RuntimeError, match="DIGraph cannot not be instantiated"):
        DIGraph()
