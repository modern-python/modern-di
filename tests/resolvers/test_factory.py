from modern_di import Container, Scope
from tests.resolvers.di_graph import DIGraph


async def test_app_scoped_factory() -> None:
    async with Container(scope=Scope.APP) as app_container:
        singleton1 = await DIGraph.singleton.async_resolve(app_container)
        singleton2 = await DIGraph.singleton.async_resolve(app_container)
        assert singleton1 is singleton2

    with Container(scope=Scope.APP) as app_container:
        singleton3 = DIGraph.singleton.sync_resolve(app_container)
        singleton4 = DIGraph.singleton.sync_resolve(app_container)
        assert singleton3 is singleton4
        assert singleton3 is not singleton1
