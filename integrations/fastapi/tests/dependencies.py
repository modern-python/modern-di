import dataclasses

import fastapi


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


def context_adapter_function(*, request: fastapi.Request, **_: object) -> str:
    return request.method
