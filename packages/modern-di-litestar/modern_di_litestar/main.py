import contextlib
import dataclasses
import typing

import litestar
from litestar.config.app import AppConfig
from litestar.di import Provide
from litestar.params import Dependency
from litestar.plugins import InitPlugin
from modern_di import AsyncContainer, providers
from modern_di import Scope as DIScope


T_co = typing.TypeVar("T_co", covariant=True)


def fetch_di_container(app_: litestar.Litestar) -> AsyncContainer:
    return typing.cast(AsyncContainer, app_.state.di_container)


@contextlib.asynccontextmanager
async def _lifespan_manager(app_: litestar.Litestar) -> typing.AsyncIterator[None]:
    container = fetch_di_container(app_)
    async with container:
        yield


class ModernDIPlugin(InitPlugin):
    __slots__ = ("container",)

    def __init__(self, container: AsyncContainer) -> None:
        self.container = container

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        app_config.state.di_container = self.container
        app_config.dependencies["di_container"] = Provide(build_di_container)
        app_config.lifespan.append(_lifespan_manager)
        return app_config


async def build_di_container(
    request: litestar.Request[typing.Any, typing.Any, typing.Any],
) -> typing.AsyncIterator[AsyncContainer]:
    context: dict[type[typing.Any], typing.Any] = {}
    scope: DIScope | None
    if isinstance(request, litestar.WebSocket):
        context[litestar.WebSocket] = request
        scope = DIScope.SESSION
    else:
        context[litestar.Request] = request
        scope = DIScope.REQUEST
    container: AsyncContainer = fetch_di_container(request.app)
    async with container.build_child_container(context=context, scope=scope) as request_container:
        yield request_container


@dataclasses.dataclass(slots=True, frozen=True)
class _Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co] | type[T_co]

    async def __call__(
        self, di_container: typing.Annotated[AsyncContainer | None, Dependency(skip_validation=True)] = None
    ) -> T_co | None:
        assert di_container
        if isinstance(self.dependency, providers.AbstractProvider):
            return await di_container.resolve_provider(self.dependency)
        return await di_container.resolve(dependency_type=self.dependency)


def FromDI(dependency: providers.AbstractProvider[T_co] | type[T_co]) -> Provide:  # noqa: N802
    return Provide(dependency=_Dependency(dependency), use_cache=False)
