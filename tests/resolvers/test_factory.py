import dataclasses

import pytest

from modern_di import Container, Scope, resolvers


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


app_factory = resolvers.Factory(Scope.APP, SimpleCreator, dep1="original")
request_factory = resolvers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)


async def test_app_factory() -> None:
    async with Container(scope=Scope.APP) as app_container:
        instance1 = await app_factory.async_resolve(app_container)
        instance2 = await app_factory.async_resolve(app_container)
        assert instance1 is not instance2

    with Container(scope=Scope.APP) as app_container:
        instance3 = app_factory.sync_resolve(app_container)
        instance4 = app_factory.sync_resolve(app_container)
        assert instance3 is not instance4
        assert instance1 is not instance3


async def test_request_factory() -> None:
    with Container(scope=Scope.APP) as app_container:
        with app_container.build_child_container() as request_container:
            instance1 = request_factory.sync_resolve(request_container)
            instance2 = request_factory.sync_resolve(request_container)
            assert instance1 is not instance2

        async with app_container.build_child_container() as request_container:
            instance3 = await request_factory.async_resolve(request_container)
            instance4 = await request_factory.async_resolve(request_container)
            assert instance3 is not instance4

        assert instance1 is not instance3


async def test_app_factory_in_request_scope() -> None:
    with Container(scope=Scope.APP) as app_container:
        with app_container.build_child_container():
            instance1 = await app_factory.async_resolve(app_container)

        async with app_container.build_child_container():
            instance2 = await app_factory.async_resolve(app_container)

        assert instance1 is not instance2


async def test_factory_overridden() -> None:
    async with Container(scope=Scope.APP) as app_container:
        instance1 = app_factory.sync_resolve(app_container)

        app_factory.override(SimpleCreator(dep1="override"), container=app_container)

        instance2 = app_factory.sync_resolve(app_container)
        instance3 = await app_factory.async_resolve(app_container)
        assert instance1 is not instance2
        assert instance2 is instance3
        assert instance2.dep1 != instance1.dep1

        app_factory.reset_override(app_container)

        instance4 = app_factory.sync_resolve(app_container)

        assert instance4.dep1 == instance1.dep1

        assert instance3 is not instance4


async def test_factory_wrong_dependency_scope() -> None:
    def some_factory(_: SimpleCreator) -> None: ...

    request_factory_ = resolvers.Factory(Scope.REQUEST, SimpleCreator, dep1="original")
    with pytest.raises(RuntimeError, match="Scope of dependency cannot be more than scope of dependent"):
        resolvers.Singleton(Scope.APP, some_factory, request_factory_.cast)
