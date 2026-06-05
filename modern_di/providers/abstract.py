import abc
import enum
import itertools
import typing

from modern_di import types


if typing.TYPE_CHECKING:
    from modern_di import Container

_provider_id_counter = itertools.count()


class AbstractProvider(abc.ABC, typing.Generic[types.T_co]):
    BASE_SLOTS: typing.ClassVar[list[str]] = ["scope", "bound_type", "provider_id"]

    def __init__(
        self,
        *,
        scope: enum.IntEnum,
        bound_type: type | None,
    ) -> None:
        self.scope = scope
        self.bound_type = bound_type
        self.provider_id: typing.Final = next(_provider_id_counter)

    @abc.abstractmethod
    def resolve(self, container: "Container") -> typing.Any: ...  # noqa: ANN401

    def get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:  # noqa: ARG002
        return {}

    def iter_validation_issues(self, container: "Container") -> typing.Iterable[Exception]:  # noqa: ARG002
        """Yield validation-time issues for this provider. Default: no issues."""
        return iter(())
