import typing

import litestar
import modern_di
from litestar import status_codes
from litestar.testing import TestClient
from modern_di import Scope, providers
from modern_di_litestar import FromDI

from tests_litestar.dependencies import DependentCreator, SimpleCreator


def context_adapter_function(*, request: litestar.Request[typing.Any, typing.Any, typing.Any], **_: object) -> str:
    return request.method


app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
request_factory = providers.Singleton(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)
action_factory = providers.Factory(Scope.ACTION, DependentCreator, dep1=app_factory.cast)
context_adapter = providers.ContextAdapter(Scope.REQUEST, context_adapter_function)


def test_factories(client: TestClient[litestar.Litestar], app: litestar.Litestar) -> None:
    @litestar.get(
        "/",
        dependencies={"app_factory_instance": FromDI(app_factory), "request_factory_instance": FromDI(request_factory)},
    )
    async def read_root(
        app_factory_instance: SimpleCreator,
        request_factory_instance: DependentCreator,
    ) -> None:
        assert isinstance(app_factory_instance, SimpleCreator)
        assert isinstance(request_factory_instance, DependentCreator)
        assert request_factory_instance.dep1 is not app_factory_instance

    app.register(read_root)

    response = client.get("/")
    assert response.status_code == status_codes.HTTP_200_OK, response.text
    assert response.json() is None


def test_context_adapter(client: TestClient[litestar.Litestar], app: litestar.Litestar) -> None:
    @litestar.get("/", dependencies={"method": FromDI(context_adapter)})
    async def read_root(method: str) -> None:
        assert method == "GET"

    app.register(read_root)

    response = client.get("/")
    assert response.status_code == status_codes.HTTP_200_OK
    assert response.json() is None


def test_factories_action_scope(client: TestClient[litestar.Litestar], app: litestar.Litestar) -> None:
    @litestar.get("/")
    async def read_root(di_container: modern_di.Container) -> None:
        with di_container.build_child_container() as action_container:
            action_factory_instance = action_container.sync_resolve_provider(action_factory)
            assert isinstance(action_factory_instance, DependentCreator)

    app.register(read_root)

    response = client.get("/")
    assert response.status_code == status_codes.HTTP_200_OK
    assert response.json() is None


def test_factory_override(
    client: TestClient[litestar.Litestar], app: litestar.Litestar, di_container: modern_di.Container
) -> None:
    mock = SimpleCreator(dep1="mock")
    di_container.override(app_factory, mock)

    @litestar.get(
        "/",
        dependencies={"app_factory_instance": FromDI(app_factory), "request_factory_instance": FromDI(request_factory)},
    )
    async def read_root(
        app_factory_instance: SimpleCreator,
        request_factory_instance: DependentCreator,
    ) -> None:
        assert isinstance(app_factory_instance, SimpleCreator)
        assert isinstance(request_factory_instance, DependentCreator)
        assert app_factory_instance.dep1 == "mock"

    app.register(read_root)

    response = client.get("/")
    assert response.status_code == status_codes.HTTP_200_OK, response.text
    assert response.json() is None
