import dataclasses
import enum
import typing
from collections.abc import Awaitable, Callable
from importlib.metadata import version

import faststream
import modern_di
from faststream.asgi import AsgiFastStream
from faststream.types import DecodedMessage
from modern_di import Container, Scope, providers


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")

_major, _minor, *_ = version("faststream").split(".")
_OLD_MIDDLEWARES = int(_major) == 0 and int(_minor) < 6  # noqa: PLR2004


class _DiMiddleware(faststream.BaseMiddleware, typing.Generic[P]):
    async def consume_scope(
        self,
        call_next: Callable[[typing.Any], Awaitable[typing.Any]],
        msg: faststream.StreamMessage[typing.Any],
    ) -> typing.AsyncIterator[DecodedMessage]:
        di_container: Container = self.faststream_context.get("di_container")
        async with di_container.build_child_container(
            scope=modern_di.Scope.REQUEST, context={"message": msg}
        ) as request_container:
            with self.faststream_context.scope("request_container", request_container):
                return typing.cast(
                    typing.AsyncIterator[DecodedMessage],
                    await call_next(msg),
                )

    if _OLD_MIDDLEWARES:  # pragma: no cover

        @property
        def faststream_context(self) -> faststream.ContextRepo:
            return typing.cast(faststream.ContextRepo, faststream.context)  # type: ignore[attr-defined]

    else:  # pragma: no cover

        @property
        def faststream_context(self) -> faststream.ContextRepo:
            return self.context


def fetch_di_container(app_: faststream.FastStream | AsgiFastStream) -> Container:
    return typing.cast(Container, app_.context.get("di_container"))


def setup_di(
    app: faststream.FastStream | AsgiFastStream, scope: enum.IntEnum = Scope.APP, container: Container | None = None
) -> Container:
    if not app.broker:
        msg = "Broker must be defined to setup DI"
        raise RuntimeError(msg)

    if not container:
        container = Container(scope=scope)
    app.context.set_global("di_container", container)
    app.on_startup(container.async_enter)
    app.after_shutdown(container.async_close)
    app.broker.add_middleware(_DiMiddleware)
    return container


@dataclasses.dataclass(slots=True, frozen=True)
class Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co]

    async def __call__(self, context: faststream.ContextRepo) -> T_co:
        request_container: modern_di.Container = context.get("request_container")
        return await self.dependency.async_resolve(request_container)


def FromDI(dependency: providers.AbstractProvider[T_co], *, use_cache: bool = True, cast: bool = False) -> T_co:  # noqa: N802
    return typing.cast(T_co, faststream.Depends(dependency=Dependency(dependency), use_cache=use_cache, cast=cast))
