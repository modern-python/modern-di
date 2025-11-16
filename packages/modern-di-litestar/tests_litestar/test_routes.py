import litestar
from litestar import status_codes
from litestar.testing import TestClient
from modern_di import AsyncContainer
from modern_di_litestar import FromDI

from tests_litestar.dependencies import Dependencies, DependentCreator, SimpleCreator


def test_factories(client: TestClient[litestar.Litestar], app: litestar.Litestar) -> None:
    @litestar.get(
        "/",
        dependencies={
            "app_factory_instance": FromDI(SimpleCreator),
            "request_factory_instance": FromDI(Dependencies.request_factory),
        },
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


def test_context_provider(client: TestClient[litestar.Litestar], app: litestar.Litestar) -> None:
    @litestar.get("/", dependencies={"method": FromDI(Dependencies.request_method)})
    async def read_root(method: str) -> None:
        assert method == "GET"

    app.register(read_root)

    response = client.get("/")
    assert response.status_code == status_codes.HTTP_200_OK, response.text
    assert response.json() is None


def test_factories_action_scope(client: TestClient[litestar.Litestar], app: litestar.Litestar) -> None:
    @litestar.get("/")
    async def read_root(di_container: AsyncContainer) -> None:
        async with di_container.build_child_container() as action_container:
            action_factory_instance = await action_container.resolve_provider(Dependencies.action_factory)
            assert isinstance(action_factory_instance, DependentCreator)

    app.register(read_root)

    response = client.get("/")
    assert response.status_code == status_codes.HTTP_200_OK
    assert response.json() is None


def test_factory_override(
    client: TestClient[litestar.Litestar], app: litestar.Litestar, di_container: AsyncContainer
) -> None:
    mock = SimpleCreator(dep1="mock")
    di_container.override(Dependencies.app_factory, mock)

    @litestar.get(
        "/",
        dependencies={
            "app_factory_instance": FromDI(Dependencies.app_factory),
            "request_factory_instance": FromDI(Dependencies.request_factory),
        },
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
