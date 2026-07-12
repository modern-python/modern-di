import abc
import enum
import itertools
import typing

from modern_di import exceptions, types
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container

_provider_id_counter = itertools.count()


class AbstractProvider(abc.ABC, typing.Generic[types.T_co]):
    __slots__ = ("_scope_defaulted", "_stamping_group", "bound_type", "provider_id", "scope")

    def __init__(
        self,
        *,
        scope: enum.IntEnum | types.UnsetType,
        bound_type: type | None,
    ) -> None:
        self._scope_defaulted = isinstance(scope, types.UnsetType)
        self.scope: enum.IntEnum = Scope.APP if isinstance(scope, types.UnsetType) else scope
        self._stamping_group: str | None = None
        self.bound_type = bound_type
        self.provider_id: typing.Final = next(_provider_id_counter)

    def _stamp_group_scope(self, scope: enum.IntEnum, group_name: str) -> None:
        """Apply a Group-level default scope; no-op when the provider's scope was chosen explicitly."""
        if not self._scope_defaulted:
            return
        if self._stamping_group is not None:
            if self.scope != scope:
                raise exceptions.GroupScopeConflictError(
                    provider_name=self.display_name,
                    first_group=self._stamping_group,
                    first_scope=self.scope,
                    second_group=group_name,
                    second_scope=scope,
                )
            return
        self.scope = scope
        self._stamping_group = group_name

    @property
    def display_name(self) -> str:
        """Human-readable name for error messages and resolution steps.

        The bound type's name when known, else the provider's repr. ``Factory`` overrides
        this to fall back to the creator's name.
        """
        return self.bound_type.__name__ if self.bound_type else repr(self)

    @property
    def definition_site(self) -> str | None:
        """``module:line`` of the provider's declaration when known; None by default (no creator)."""
        return None

    @abc.abstractmethod
    def resolve(self, container: "Container") -> typing.Any: ...  # noqa: ANN401

    def get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:  # noqa: ARG002
        return {}

    def redirect_target(self, container: "Container") -> "AbstractProvider[typing.Any] | None":  # noqa: ARG002
        """Return the provider this transparently forwards to, or None if resolution terminates here."""
        return None

    def iter_validation_issues(self, container: "Container") -> typing.Iterable[Exception]:  # noqa: ARG002
        """Yield validation-time issues for this provider. Default: no issues."""
        return iter(())
