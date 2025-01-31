import dataclasses
import enum
import typing

import litestar
from litestar.di import Provide
from litestar.params import Dependency
from modern_di import Container, providers
from modern_di import Scope as DIScope


T_co = typing.TypeVar("T_co", covariant=True)


def setup_di(app: litestar.Litestar, scope: enum.IntEnum = DIScope.APP) -> Container:
    app.state.di_container = Container(scope=scope)
    return app.state.di_container


def prepare_di_dependencies() -> dict[str, Provide]:
    return {"di_container": Provide(build_di_container)}


def fetch_di_container(app: litestar.Litestar) -> Container:
    return typing.cast(Container, app.state.di_container)


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
