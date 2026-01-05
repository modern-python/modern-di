import dataclasses
import typing
from collections.abc import Awaitable, Callable
from importlib.metadata import version

import faststream
import modern_di
from faststream.asgi import AsgiFastStream
from faststream.types import DecodedMessage
from modern_di import Container, providers


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
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    async def consume_scope(
        self,
        call_next: Callable[[typing.Any], Awaitable[typing.Any]],
        msg: faststream.StreamMessage[typing.Any],
    ) -> typing.AsyncIterator[DecodedMessage]:
        request_container = self.di_container.build_child_container(
            scope=modern_di.Scope.REQUEST, context={faststream.StreamMessage: msg}
        )
        with self.faststream_context.scope("request_container", request_container):
            return typing.cast(
                typing.AsyncIterator[DecodedMessage],
                await call_next(msg),
            )

    if _OLD_MIDDLEWARES:  # pragma: no cover

        @property
        def faststream_context(self) -> faststream.ContextRepo:
            return typing.cast(faststream.ContextRepo, faststream.context)  # type: ignore[attr-defined]

    else:

        @property
        def faststream_context(self) -> faststream.ContextRepo:
            return self.context


def fetch_di_container(app_: faststream.FastStream | AsgiFastStream) -> Container:
    return typing.cast(Container, app_.context.get("di_container"))


def setup_di(
    app: faststream.FastStream | AsgiFastStream,
    container: Container,
) -> Container:
    if not app.broker:
        msg = "Broker must be defined to setup DI"
        raise RuntimeError(msg)

    app.context.set_global("di_container", container)
    app.broker.add_middleware(_DIMiddlewareFactory(container))
    return container


@dataclasses.dataclass(slots=True, frozen=True)
class Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co] | type[T_co]

    async def __call__(self, context: faststream.ContextRepo) -> T_co:
        request_container: Container = context.get("request_container")
        if isinstance(self.dependency, providers.AbstractProvider):
            return request_container.resolve_provider(self.dependency)
        return request_container.resolve(dependency_type=self.dependency)


def FromDI(  # noqa: N802
    dependency: providers.AbstractProvider[T_co] | type[T_co], *, use_cache: bool = True, cast: bool = False
) -> T_co:
    return typing.cast(T_co, faststream.Depends(dependency=Dependency(dependency), use_cache=use_cache, cast=cast))
