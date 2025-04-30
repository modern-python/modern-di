import dataclasses
import enum
import typing
from collections.abc import Awaitable, Callable
from importlib.metadata import version

import faststream
import modern_di
from faststream.broker.message import StreamMessage
from faststream.types import DecodedMessage
from modern_di import Container, Scope, providers


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")

_major, _minor, *_ = version("faststream").split(".")
_OLD_MIDDLEWARES = int(_major) == 0 and int(_minor) < 6  # noqa: PLR2004


class _DIMiddlewareFactory:
    __slots__ = ("di_container",)

    def __init__(self, di_container: Container) -> None:
        self.di_container = di_container

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> "_DiMiddleware[P]":
        return _DiMiddleware(self.di_container, *args, **kwargs)


class _DiMiddleware(faststream.BaseMiddleware, typing.Generic[P]):
    def __init__(self, di_container: Container, *args: P.args, **kwargs: P.kwargs) -> None:
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

    if _OLD_MIDDLEWARES:  # pragma: no cover

        @property
        def faststream_context(self) -> faststream.ContextRepo:
            return faststream.context

    else:  # pragma: no cover

        @property
        def faststream_context(self) -> faststream.ContextRepo:
            return self.context  # type: ignore[attr-defined,no-any-return]


def setup_di(app: faststream.FastStream, scope: enum.IntEnum = Scope.APP) -> Container:
    if not app.broker:
        msg = "Broker must be defined to setup DI"
        raise RuntimeError(msg)

    container = Container(scope=scope)
    app.on_startup(container.async_enter)
    app.after_shutdown(container.async_close)
    app.broker.add_middleware(_DIMiddlewareFactory(container))
    return container


@dataclasses.dataclass(slots=True, frozen=True)
class Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co]

    async def __call__(self, context: faststream.ContextRepo) -> T_co:
        request_container: modern_di.Container = context.get("request_container")
        return await self.dependency.async_resolve(request_container)


def FromDI(dependency: providers.AbstractProvider[T_co], *, use_cache: bool = True, cast: bool = False) -> T_co:  # noqa: N802
    return typing.cast(T_co, faststream.Depends(dependency=Dependency(dependency), use_cache=use_cache, cast=cast))
