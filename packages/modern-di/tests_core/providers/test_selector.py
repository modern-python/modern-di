import pytest
from modern_di import Container, Scope, providers


def selector_function(*, option: str, **_: object) -> "str":
    return option


app_factory = providers.Factory(Scope.APP, lambda: "app")
request_factory = providers.Factory(Scope.APP, lambda: "request")
app_selector = providers.Selector(Scope.APP, selector_function, app=app_factory, request=request_factory)
request_selector = providers.Selector(Scope.REQUEST, selector_function, app=app_factory, request=request_factory)


async def test_selector() -> None:
    async with Container(scope=Scope.APP, context={"option": "app"}) as app_container:
        instance1 = await app_container.async_resolve_provider(app_selector)
        instance2 = app_container.sync_resolve_provider(app_selector)
        assert instance1 == instance2 == "app"


async def test_selector_in_request_scope() -> None:
    async with (
        Container(scope=Scope.APP) as app_container,
        app_container.build_child_container(context={"option": "request"}, scope=Scope.REQUEST) as request_container,
    ):
        instance1 = await request_container.async_resolve_provider(request_selector)
        instance2 = request_container.sync_resolve_provider(request_selector)
        assert instance1 == instance2 == "request"


async def test_selector_no_match() -> None:
    async with Container(scope=Scope.APP, context={"option": "wrong"}) as app_container:
        with pytest.raises(RuntimeError, match="No provider matches wrong"):
            await app_container.async_resolve_provider(app_selector)

        with pytest.raises(RuntimeError, match="No provider matches wrong"):
            app_container.sync_resolve_provider(app_selector)


async def test_selector_wrong_scope() -> None:
    request_factory_ = providers.Factory(Scope.REQUEST, lambda: "")
    with pytest.raises(RuntimeError, match="Scope of request is REQUEST and current scope is APP"):
        providers.Selector(Scope.APP, lambda: "", request=request_factory_)
