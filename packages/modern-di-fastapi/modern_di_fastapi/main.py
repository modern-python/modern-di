import contextlib
import dataclasses
import typing

import fastapi
from fastapi.routing import _merge_lifespan_context
from modern_di import Container, Scope, providers
from starlette.requests import HTTPConnection


T_co = typing.TypeVar("T_co", covariant=True)


fastapi_request_provider = providers.ContextProvider(scope=Scope.REQUEST, context_type=fastapi.Request)
fastapi_websocket_provider = providers.ContextProvider(scope=Scope.SESSION, context_type=fastapi.WebSocket)


def fetch_di_container(app_: fastapi.FastAPI) -> Container:
    return typing.cast(Container, app_.state.di_container)


@contextlib.asynccontextmanager
async def _lifespan_manager(app_: fastapi.FastAPI) -> typing.AsyncIterator[None]:
    container = fetch_di_container(app_)
    try:
        yield
    finally:
        await container.close_async()


def setup_di(app: fastapi.FastAPI, container: Container) -> Container:
    app.state.di_container = container
    container.providers_registry.add_providers(fastapi_request_provider, fastapi_websocket_provider)
    old_lifespan_manager = app.router.lifespan_context
    app.router.lifespan_context = _merge_lifespan_context(
        old_lifespan_manager,
        _lifespan_manager,
    )
    return container


async def build_di_container(connection: HTTPConnection) -> typing.AsyncIterator[Container]:
    context: dict[type[typing.Any], typing.Any] = {}
    scope: Scope | None = None
    if isinstance(connection, fastapi.Request):
        scope = Scope.REQUEST
        context[fastapi.Request] = connection
    elif isinstance(connection, fastapi.WebSocket):
        context[fastapi.WebSocket] = connection
        scope = Scope.SESSION
    container = fetch_di_container(connection.app).build_child_container(context=context, scope=scope)
    try:
        yield container
    finally:
        await container.close_async()


@dataclasses.dataclass(slots=True, frozen=True)
class Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co] | type[T_co]

    async def __call__(
        self, request_container: typing.Annotated[Container, fastapi.Depends(build_di_container)]
    ) -> T_co:
        if isinstance(self.dependency, providers.AbstractProvider):
            return request_container.resolve_provider(self.dependency)
        return request_container.resolve(dependency_type=self.dependency)


def FromDI(dependency: providers.AbstractProvider[T_co] | type[T_co], *, use_cache: bool = True) -> T_co:  # noqa: N802
    return typing.cast(T_co, fastapi.Depends(dependency=Dependency(dependency), use_cache=use_cache))
