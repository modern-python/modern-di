import abc
import typing
import uuid

from modern_di import types
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


class AbstractProvider(abc.ABC, typing.Generic[types.T_co]):
    BASE_SLOTS: typing.ClassVar[list[str]] = ["scope", "bound_type", "provider_id", "qualifier", "qualifiers"]

    def __init__(
        self,
        *,
        scope: Scope,
        bound_type: type | None,
        qualifier: str | None = None,
        qualifiers: dict[typing.Type[typing.Any], str] | None = None,
    ) -> None:
        self.scope = scope
        self.bound_type = bound_type
        self.provider_id: typing.Final = str(uuid.uuid4())
        self.qualifier = qualifier
        self.qualifiers = qualifiers or {}

    @abc.abstractmethod
    def resolve(self, container: "Container") -> typing.Any: ...  # noqa: ANN401
