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
    __slots__ = ("_explicit_scope", "_group_claim", "_registered", "bound_type", "provider_id")

    _takes_group_scope: typing.ClassVar[bool] = True
    """Whether a Group-level default scope applies. False when the effective scope is derived."""

    def __init__(
        self,
        *,
        scope: enum.IntEnum | types.UnsetType,
        bound_type: type | None,
    ) -> None:
        self._explicit_scope: enum.IntEnum | None = scope if isinstance(scope, enum.IntEnum) else None
        self._group_claim: tuple[enum.IntEnum, str] | None = None
        self._registered = False
        self.bound_type = bound_type
        self.provider_id: typing.Final = next(_provider_id_counter)

    @property
    def scope(self) -> enum.IntEnum:
        """The effective scope: the provider's own ``scope=``, else a Group default, else ``Scope.APP``."""
        if self._explicit_scope is not None:
            return self._explicit_scope
        if self._group_claim is not None:
            return self._group_claim[0]
        return Scope.APP

    def _stamp_group_scope(self, scope: enum.IntEnum, group_name: str) -> None:
        """Record a Group-level default scope; no-op unless this provider's scope is still an unclaimed default.

        Frozen once registered: a compiled resolver captures `scope`, so a later change would apply
        only to resolvers compiled after it.
        """
        if not self._takes_group_scope or self._explicit_scope is not None:
            return
        if self._group_claim is not None:
            first_scope, first_group = self._group_claim
            if first_scope != scope:
                raise exceptions.GroupScopeConflictError(
                    provider_name=self.display_name,
                    first_group=first_group,
                    first_scope=first_scope,
                    second_group=group_name,
                    second_scope=scope,
                )
            return
        if self._registered and self.scope != scope:
            raise exceptions.ProviderScopeFrozenError(
                provider_name=self.display_name,
                group_name=group_name,
                current_scope=self.scope,
                new_scope=scope,
            )
        self._group_claim = (scope, group_name)

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

    def get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:  # noqa: ARG002
        return {}

    def redirect_target(self, container: "Container") -> "AbstractProvider[typing.Any] | None":  # noqa: ARG002
        """Return the provider this transparently forwards to, or None if resolution terminates here."""
        return None

    def iter_validation_issues(self, container: "Container") -> typing.Iterable[Exception]:  # noqa: ARG002
        """Yield validation-time issues for this provider. Default: no issues."""
        return iter(())
