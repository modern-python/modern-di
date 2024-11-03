import dataclasses
import typing

import fastapi
from modern_di import Container, Scope, providers


T_co = typing.TypeVar("T_co", covariant=True)


def setup_di(app: fastapi.FastAPI) -> Container:
    app.state.di_container = Container(scope=Scope.APP)
    return app.state.di_container


def fetch_di_container(app: fastapi.FastAPI) -> Container:
    return typing.cast(Container, app.state.di_container)


async def _build_request_container(request: fastapi.Request) -> typing.AsyncIterator[Container]:
    container: Container = fetch_di_container(request.app)
    async with container.build_child_container(context={"request": request}) as request_container:
        yield request_container


@dataclasses.dataclass(slots=True, frozen=True)
class Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co]

    async def __call__(
        self, request_container: typing.Annotated[Container, fastapi.Depends(_build_request_container)]
    ) -> T_co:
        return await self.dependency.async_resolve(request_container)


def Provide(dependency: providers.AbstractProvider[T_co], *, use_cache: bool = True) -> T_co:  # noqa: N802
    return typing.cast(T_co, fastapi.Depends(dependency=Dependency(dependency), use_cache=use_cache))
