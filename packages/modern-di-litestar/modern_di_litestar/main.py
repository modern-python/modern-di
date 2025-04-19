import contextlib
import dataclasses
import enum
import typing

import litestar
from litestar.config.app import AppConfig
from litestar.di import Provide
from litestar.params import Dependency
from litestar.plugins import InitPlugin
from modern_di import Container, providers
from modern_di import Scope as DIScope


T_co = typing.TypeVar("T_co", covariant=True)


def fetch_di_container(app_: litestar.Litestar) -> Container:
    return typing.cast(Container, app_.state.di_container)


@contextlib.asynccontextmanager
async def _lifespan_manager(app_: litestar.Litestar) -> typing.AsyncIterator[None]:
    container = fetch_di_container(app_)
    async with container:
        yield


class ModernDIPlugin(InitPlugin):
    __slots__ = ("scope",)

    def __init__(self, scope: enum.IntEnum = DIScope.APP) -> None:
        self.scope = scope

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        app_config.state.di_container = Container(scope=self.scope)
        app_config.dependencies["di_container"] = Provide(build_di_container)
        app_config.lifespan.append(_lifespan_manager)
        return app_config


async def build_di_container(
    request: litestar.Request[typing.Any, typing.Any, typing.Any],
) -> typing.AsyncIterator[Container]:
    context: dict[str, typing.Any] = {}
    scope: DIScope | None
    if isinstance(request, litestar.WebSocket):
        context["websocket"] = request
        scope = DIScope.SESSION
    else:
        context["request"] = request
        scope = DIScope.REQUEST
    container: Container = fetch_di_container(request.app)
    async with container.build_child_container(context=context, scope=scope) as request_container:
        yield request_container


@dataclasses.dataclass(slots=True, frozen=True)
class _Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co]

    async def __call__(self, di_container: typing.Annotated[Container | None, Dependency()] = None) -> T_co | None:
        assert di_container
        return await self.dependency.async_resolve(di_container)


def FromDI(dependency: providers.AbstractProvider[T_co]) -> Provide:  # noqa: N802
    return Provide(dependency=_Dependency(dependency), use_cache=False)
