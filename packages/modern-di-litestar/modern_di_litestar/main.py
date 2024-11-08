import dataclasses
import enum
import typing

import litestar
from litestar.di import Provide
from litestar.enums import ScopeType
from litestar.types import ASGIApp, Receive, Scope, Send
from modern_di import Container, providers
from modern_di import Scope as DIScope


T_co = typing.TypeVar("T_co", covariant=True)


def setup_di(app: litestar.Litestar, scope: enum.IntEnum = DIScope.APP) -> Container:
    app.asgi_handler = make_add_request_container_middleware(
        app.asgi_handler,
    )
    app.state.di_container = Container(scope=scope)
    return app.state.di_container


def fetch_di_container(app: litestar.Litestar) -> Container:
    return typing.cast(Container, app.state.di_container)


def make_add_request_container_middleware(app: ASGIApp) -> ASGIApp:
    async def middleware(scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != ScopeType.HTTP:
            await app(scope, receive, send)
            return

        request: litestar.Request[typing.Any, typing.Any, typing.Any] = litestar.Request(scope)
        di_container = fetch_di_container(request.app)

        async with di_container.build_child_container(
            scope=DIScope.REQUEST, context={"request": request}
        ) as request_container:
            request.state.di_container = request_container
            await app(scope, receive, send)

    return middleware


@dataclasses.dataclass(slots=True, frozen=True)
class Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co]

    async def __call__(self, request: litestar.Request[typing.Any, typing.Any, typing.Any]) -> T_co:
        return await self.dependency.async_resolve(request.state.di_container)


def FromDI(dependency: providers.AbstractProvider[T_co], *, use_cache: bool = True) -> Provide:  # noqa: N802
    return Provide(dependency=Dependency(dependency), use_cache=use_cache)
