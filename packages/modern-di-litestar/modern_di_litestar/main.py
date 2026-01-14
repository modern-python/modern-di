import contextlib
import dataclasses
import typing

import litestar
from litestar.config.app import AppConfig
from litestar.di import Provide
from litestar.params import Dependency
from litestar.plugins import InitPlugin
from modern_di import Container, providers
from modern_di.scope import Scope
from modern_di.scope import Scope as DIScope


T_co = typing.TypeVar("T_co", covariant=True)


litestar_request = providers.ContextProvider(scope=Scope.REQUEST, context_type=litestar.Request)
litestar_websocket = providers.ContextProvider(scope=Scope.SESSION, context_type=litestar.WebSocket)


def fetch_di_container(app_: litestar.Litestar) -> Container:
    return typing.cast(Container, app_.state.di_container)


@contextlib.asynccontextmanager
async def _lifespan_manager(app_: litestar.Litestar) -> typing.AsyncIterator[None]:
    container = fetch_di_container(app_)
    try:
        yield
    finally:
        await container.close_async()


class ModernDIPlugin(InitPlugin):
    __slots__ = ("container",)

    def __init__(self, container: Container) -> None:
        self.container = container

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        self.container.providers_registry.add_providers(
            litestar_request=litestar_request, litestar_websocket=litestar_websocket
        )
        app_config.state.di_container = self.container
        app_config.dependencies["di_container"] = Provide(build_di_container)
        app_config.lifespan.append(_lifespan_manager)
        return app_config


async def build_di_container(
    request: litestar.Request[typing.Any, typing.Any, typing.Any],
) -> typing.AsyncIterator[Container]:
    context: dict[type[typing.Any], typing.Any] = {}
    scope: DIScope | None
    if isinstance(request, litestar.WebSocket):
        context[litestar.WebSocket] = request
        scope = DIScope.SESSION
    else:
        context[litestar.Request] = request
        scope = DIScope.REQUEST
    container = fetch_di_container(request.app).build_child_container(context=context, scope=scope)
    try:
        yield container
    finally:
        await container.close_async()


@dataclasses.dataclass(slots=True, frozen=True)
class _Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co] | type[T_co]

    async def __call__(
        self, di_container: typing.Annotated[Container, Dependency(skip_validation=True)]
    ) -> T_co | None:
        if isinstance(self.dependency, providers.AbstractProvider):
            return di_container.resolve_provider(self.dependency)
        return di_container.resolve(dependency_type=self.dependency)


def FromDI(dependency: providers.AbstractProvider[T_co] | type[T_co]) -> Provide:  # noqa: N802
    return Provide(dependency=_Dependency(dependency), use_cache=False)
