import typing

import modern_di
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


class ContainerMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request = Request(scope, receive=receive, send=send)
        context: dict[str, typing.Any] = {"request": request}

        container: modern_di.Container = request.app.state.modern_di_container
        async with container.build_child_container(context=context) as request_container:
            request.state.modern_di_container = request_container
            return await self.app(scope, receive, send)
