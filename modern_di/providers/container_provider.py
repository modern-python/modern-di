import typing

from modern_di.providers import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


class _ContainerProvider(AbstractProvider[typing.Any]):
    __slots__ = AbstractProvider.BASE_SLOTS

    def __init__(self) -> None:
        super().__init__(scope=Scope.APP, bound_type=None)

    def resolve(self, container: "Container") -> "Container":
        return container

    def validate(self, _: "Container") -> dict[str, typing.Any]:
        return {"self": self}


container_provider = _ContainerProvider()
