import dataclasses
import enum
import importlib
import typing
from collections.abc import Awaitable, Callable

import faststream
import modern_di
from faststream import BaseMiddleware, ContextRepo
from faststream.broker.message import StreamMessage
from faststream.types import DecodedMessage
from modern_di import Container, Scope, providers


T_co = typing.TypeVar("T_co", covariant=True)

FASTSTREAM_VERSION = importlib.metadata.version("faststream")
major, minor, *_ = FASTSTREAM_VERSION.split(".")
_FASTSTREAM_MAJOR, _FASTSTREAM_MINOR = int(major), int(minor)


class DIMiddleware:
    __slots__ = ("di_container",)

    def __init__(self, di_container: Container) -> None:
        self.di_container = di_container

    # Consumes args, kwargs due it has no matter for modern-di logic
    # and allows to be compatible with future FastStreamd middlewares signature
    def __call__(self, *args: typing.Any, **kwargs: typing.Any) -> "_DiMiddleware":  # noqa: ANN401
        return _DiMiddleware(*args, di_container=self.di_container, **kwargs)


class _DiMiddleware(BaseMiddleware):
    def __init__(self, *args: typing.Any, di_container: Container, **kwargs: typing.Any) -> None:  # noqa: ANN401
        self.di_container = di_container
        super().__init__(*args, **kwargs)

    async def consume_scope(
        self,
        call_next: Callable[[typing.Any], Awaitable[typing.Any]],
        msg: StreamMessage[typing.Any],
    ) -> typing.AsyncIterator[DecodedMessage]:
        async with self.di_container.build_child_container(
            scope=modern_di.Scope.REQUEST, context={"message": StreamMessage[typing.Any]}
        ) as request_container:
            with self.faststream_context.scope("request_container", request_container):
                return typing.cast(
                    typing.AsyncIterator[DecodedMessage],
                    await call_next(msg),
                )

    if _FASTSTREAM_MAJOR == 0 and _FASTSTREAM_MINOR < 6:  # noqa: PLR2004

        @property
        def faststream_context(self) -> ContextRepo:
            return faststream.context

    else:

        @property
        def faststream_context(self) -> ContextRepo:
            return self.context  # type: ignore[attr-defined,no-any-return]


def setup_di(app: faststream.FastStream, scope: enum.IntEnum = Scope.APP) -> Container:
    assert app.broker, "broker must be defined to setup DI"

    container = Container(scope=scope)
    app.on_startup(container.__aenter__)
    app.after_shutdown(container.async_close)
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
