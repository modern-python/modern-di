import dataclasses
import enum
import typing
from collections.abc import Awaitable, Callable

import faststream
import modern_di
import typing_extensions
from faststream import BaseMiddleware, ContextRepo
from faststream.broker.message import StreamMessage
from faststream.types import DecodedMessage
from modern_di import Container, Scope, providers


T_co = typing.TypeVar("T_co", covariant=True)


class DIMiddleware(BaseMiddleware):
    def __init__(self, di_container: Container) -> None:
        self.di_container = di_container

    def __call__(self, msg: typing.Any | None = None) -> typing_extensions.Self:  # noqa: ANN401
        self.msg = msg
        return self

    async def consume_scope(
        self,
        call_next: Callable[[typing.Any], Awaitable[typing.Any]],
        msg: StreamMessage[typing.Any],
    ) -> typing.AsyncIterator[DecodedMessage]:
        async with self.di_container.build_child_container(
            scope=modern_di.Scope.REQUEST, context={"message": StreamMessage[typing.Any]}
        ) as request_container:
            with faststream.context.scope("request_container", request_container):
                return typing.cast(
                    typing.AsyncIterator[DecodedMessage],
                    await call_next(msg),
                )


def setup_di(app: faststream.FastStream, scope: enum.IntEnum = Scope.APP) -> Container:
    assert app.broker, "broker must be defined to setup DI"

    container = Container(scope=scope)
    app.broker.add_middleware(DIMiddleware(container))
    return container


@dataclasses.dataclass(slots=True, frozen=True)
class Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co]

    async def __call__(self, context: ContextRepo) -> T_co:
        request_container: modern_di.Container = context.get("request_container")
        return await self.dependency.async_resolve(request_container)


def FromDI(dependency: providers.AbstractProvider[T_co], *, use_cache: bool = True, cast: bool = True) -> T_co:  # noqa: N802
    return typing.cast(T_co, faststream.Depends(dependency=Dependency(dependency), use_cache=use_cache, cast=cast))
