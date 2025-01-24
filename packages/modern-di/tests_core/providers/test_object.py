from modern_di import Container, Scope, providers


instance = ["some item"]


object_provider = providers.Object(Scope.APP, instance)


async def test_object_provider() -> None:
    async with Container(scope=Scope.APP) as app_container:
        instance1 = await object_provider.async_resolve(app_container)
        instance2 = object_provider.sync_resolve(app_container)

        assert instance1 is instance2 is instance


async def test_object_provider_overridden() -> None:
    async with Container(scope=Scope.APP) as app_container:
        instance1 = await object_provider.async_resolve(app_container)

        object_provider.override(["override"], container=app_container)

        instance2 = await object_provider.async_resolve(app_container)
        instance3 = object_provider.sync_resolve(app_container)

        assert instance1 is instance
        assert instance2 is not instance
        assert instance2 is instance3
