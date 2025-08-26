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
        instance1 = await app_container.async_resolve_provider(object_provider)

        app_container.override(object_provider, ["override"])

        instance2 = await app_container.async_resolve_provider(object_provider)
        instance3 = app_container.sync_resolve_provider(object_provider)

        assert instance1 is instance
        assert instance2 is not instance
        assert instance2 is instance3
