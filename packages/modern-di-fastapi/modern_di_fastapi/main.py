import contextlib
import dataclasses
import typing

import fastapi
from fastapi.routing import _merge_lifespan_context
from modern_di import AsyncContainer, Scope, providers
from starlette.requests import HTTPConnection


T_co = typing.TypeVar("T_co", covariant=True)


def fetch_di_container(app_: fastapi.FastAPI) -> AsyncContainer:
    return typing.cast(AsyncContainer, app_.state.di_container)


@contextlib.asynccontextmanager
async def _lifespan_manager(app_: fastapi.FastAPI) -> typing.AsyncIterator[None]:
    async with fetch_di_container(app_):
        yield


def setup_di(app: fastapi.FastAPI, container: AsyncContainer) -> AsyncContainer:
    app.state.di_container = container
    old_lifespan_manager = app.router.lifespan_context
    app.router.lifespan_context = _merge_lifespan_context(
        old_lifespan_manager,
        _lifespan_manager,
    )
    return container


async def build_di_container(connection: HTTPConnection) -> typing.AsyncIterator[AsyncContainer]:
    context: dict[type[typing.Any], typing.Any] = {}
    scope: Scope | None = None
    if isinstance(connection, fastapi.Request):
        scope = Scope.REQUEST
        context[fastapi.Request] = connection
    elif isinstance(connection, fastapi.WebSocket):
        context[fastapi.WebSocket] = connection
        scope = Scope.SESSION
    container: AsyncContainer = fetch_di_container(connection.app)
    async with container.build_child_container(context=context, scope=scope) as request_container:
        yield request_container


@dataclasses.dataclass(slots=True, frozen=True)
class Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co] | type[T_co]

    async def __call__(
        self, request_container: typing.Annotated[AsyncContainer, fastapi.Depends(build_di_container)]
    ) -> T_co:
        if isinstance(self.dependency, providers.AbstractProvider):
            return await request_container.resolve_provider(self.dependency)
        return await request_container.resolve(dependency_type=self.dependency)


def FromDI(dependency: providers.AbstractProvider[T_co] | type[T_co], *, use_cache: bool = True) -> T_co:  # noqa: N802
    return typing.cast(T_co, fastapi.Depends(dependency=Dependency(dependency), use_cache=use_cache))
