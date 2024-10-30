import dataclasses
import typing

import fastapi
import modern_di


T_co = typing.TypeVar("T_co", covariant=True)


@dataclasses.dataclass(slots=True, frozen=True)
class Dependency(typing.Generic[T_co]):
    dependency: modern_di.resolvers.AbstractResolver[T_co]

    async def __call__(self, request: fastapi.Request) -> T_co:
        return await self.dependency.async_resolve(request.state.modern_di_container)


def FromDI(dependency: modern_di.resolvers.AbstractResolver[T_co], *, use_cache: bool = True) -> T_co:  # noqa: N802
    return typing.cast(T_co, fastapi.Depends(dependency=Dependency(dependency), use_cache=use_cache))


def setup_modern_di(container: modern_di.Container, app: fastapi.FastAPI) -> None:
    app.state.modern_di_container = container
