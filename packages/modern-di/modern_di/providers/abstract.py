import abc
import typing
import uuid

from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


T_co = typing.TypeVar("T_co", covariant=True)


class AbstractProvider(abc.ABC, typing.Generic[T_co]):
    BASE_SLOTS: typing.ClassVar[list[str]] = ["scope", "bound_type", "provider_id"]

    def __init__(
        self,
        *,
        scope: Scope,
        bound_type: type | None,
    ) -> None:
        self.scope = scope
        self.bound_type = bound_type
        self.provider_id: typing.Final = str(uuid.uuid4())

    @abc.abstractmethod
    def resolve(self, container: "Container") -> typing.Any: ...  # noqa: ANN401
