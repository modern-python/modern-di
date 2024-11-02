import dataclasses
import typing

import fastapi
from modern_di import Container, providers


T_co = typing.TypeVar("T_co", covariant=True)


def save_di_container(obj: fastapi.FastAPI | fastapi.Request, container: Container) -> None:
    obj.state.di_container = container


def fetch_di_container(obj: fastapi.FastAPI | fastapi.Request) -> Container:
    return typing.cast(Container, obj.state.di_container)


@dataclasses.dataclass(slots=True, frozen=True)
class Dependency(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co]

    async def __call__(self, request: fastapi.Request) -> T_co:
        return await self.dependency.async_resolve(fetch_di_container(request))


def FromDI(dependency: providers.AbstractProvider[T_co], *, use_cache: bool = True) -> T_co:  # noqa: N802
    return typing.cast(T_co, fastapi.Depends(dependency=Dependency(dependency), use_cache=use_cache))


async def enter_di_request_scope(request: fastapi.Request) -> typing.AsyncIterator[None]:
    container: Container = fetch_di_container(request.app)
    async with container.build_child_container(context={"request": request}) as request_container:
        save_di_container(request, request_container)
        try:
            yield
        finally:
            del request.state.di_container
