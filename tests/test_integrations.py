from modern_di import Scope, providers
from modern_di.integrations import ConnectionMatch, bind


class _Request:
    pass


def test_bind_derives_scope_and_context_from_provider() -> None:
    provider = providers.ContextProvider(_Request, scope=Scope.REQUEST)
    connection = _Request()

    match = bind(provider, connection)

    assert match == ConnectionMatch(scope=Scope.REQUEST, context={_Request: connection})
