import dataclasses
import enum
import typing

import fastapi
from modern_di import Container, Scope, providers
from starlette.requests import HTTPConnection


T_co = typing.TypeVar("T_co", covariant=True)


def setup_di(app: fastapi.FastAPI, scope: enum.IntEnum = Scope.APP) -> Container:
    app.state.di_container = Container(scope=scope)
    return app.state.di_container


def fetch_di_container(app: fastapi.FastAPI) -> Container:
    return typing.cast(Container, app.state.di_container)


async def build_di_container(connection: HTTPConnection) -> typing.AsyncIterator[Container]:
    context: dict[str, typing.Any] = {}
    scope: Scope | None = None
    if isinstance(connection, fastapi.Request):
        scope = Scope.REQUEST
        context["request"] = connection
    elif isinstance(connection, fastapi.WebSocket):
        context["websocket"] = connection
        scope = Scope.SESSION
    container: Container = fetch_di_container(connection.app)
    async with container.build_child_container(context=context, scope=scope) as request_container:
        yield request_container


@dataclasses.dataclass(slots=True, frozen=True)
class Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co]

    async def __call__(
        self, request_container: typing.Annotated[Container, fastapi.Depends(build_di_container)]
    ) -> T_co:
        return await self.dependency.async_resolve(request_container)


def FromDI(dependency: providers.AbstractProvider[T_co], *, use_cache: bool = True) -> T_co:  # noqa: N802
    return typing.cast(T_co, fastapi.Depends(dependency=Dependency(dependency), use_cache=use_cache))
