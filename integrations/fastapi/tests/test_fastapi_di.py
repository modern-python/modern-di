import typing

import fastapi
import httpx
from modern_di import Scope, providers
from starlette import status

from modern_di_fastapi import Provide
from tests.dependencies import DependentCreator, SimpleCreator, context_adapter_function


app_factory = providers.Factory(Scope.APP, SimpleCreator, dep1="original")
request_factory = providers.Factory(Scope.REQUEST, DependentCreator, dep1=app_factory.cast)
context_adapter = providers.ContextAdapter(Scope.REQUEST, context_adapter_function)


async def test_read_main(client: httpx.AsyncClient, app: fastapi.FastAPI) -> None:
    @app.get("/")
    async def read_root(
        app_factory_instance: typing.Annotated[SimpleCreator, Provide(app_factory)],
        request_factory_instance: typing.Annotated[DependentCreator, Provide(request_factory)],
        method: typing.Annotated[str, Provide(context_adapter)],
    ) -> str:
        assert isinstance(app_factory_instance, SimpleCreator)
        assert isinstance(request_factory_instance, DependentCreator)
        return method

    response = await client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == "GET"
