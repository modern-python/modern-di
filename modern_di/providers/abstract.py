import abc
import enum
import itertools
import typing

from modern_di import types


if typing.TYPE_CHECKING:
    from modern_di import Container

_provider_id_counter = itertools.count()


class AbstractProvider(abc.ABC, typing.Generic[types.T_co]):
    __slots__ = ("bound_type", "provider_id", "scope")

    def __init__(
        self,
        *,
        scope: enum.IntEnum,
        bound_type: type | None,
    ) -> None:
        self.scope = scope
        self.bound_type = bound_type
        self.provider_id: typing.Final = next(_provider_id_counter)

    @property
    def display_name(self) -> str:
        """Human-readable name for error messages and resolution steps.

        The bound type's name when known, else the provider's repr. ``Factory`` overrides
        this to fall back to the creator's name.
        """
        return self.bound_type.__name__ if self.bound_type else repr(self)

    @abc.abstractmethod
    def resolve(self, container: "Container") -> typing.Any: ...  # noqa: ANN401

    def get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:  # noqa: ARG002
        return {}

    def iter_validation_issues(self, container: "Container") -> typing.Iterable[Exception]:  # noqa: ARG002
        """Yield validation-time issues for this provider. Default: no issues."""
        return iter(())

    def effective_scope(self, container: "Container") -> enum.IntEnum:  # noqa: ARG002
        """Scope used for validate()'s scope-ordering check.

        Transparent redirects (Alias) override this to report the scope of what they
        ultimately resolve to, so callers are checked against the real target's scope.
        """
        return self.scope
