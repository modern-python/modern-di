import enum
import itertools
import typing

from modern_di import exceptions, types
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container

_provider_id_counter = itertools.count()


class AbstractProvider(typing.Generic[types.T_co]):
    __slots__ = ("_bound_type", "_explicit_scope", "_group_claim", "_provider_id", "_registered")

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
        self._bound_type = bound_type
        self._provider_id = next(_provider_id_counter)

    @property
    def bound_type(self) -> type | None:
        """The type this provider is registered under, or ``None`` when it resolves by reference only."""
        return self._bound_type

    @property
    def provider_id(self) -> int:
        """A process-unique id."""
        return self._provider_id

    @property
    def scope(self) -> enum.IntEnum:
        """The effective scope: the provider's own ``scope=``, else a Group default, else ``Scope.APP``."""
        if self._explicit_scope is not None:
            return self._explicit_scope
        if self._group_claim is not None:
            return self._group_claim[0]
        return Scope.APP

    def _mark_registered(self) -> None:
        """Latch this provider as registered; freezes `scope` against a later Group re-stamp."""
        self._registered = True

    def _stamp_group_scope(self, scope: enum.IntEnum, group_name: str) -> None:
        """Record a Group-level default scope; a no-op unless the scope is still an unclaimed default.

        Frozen once registered: a compiled resolver captures `scope`.
        """
        if not self._takes_group_scope or self._explicit_scope is not None:
            return
        if self._group_claim is not None:
            first_scope, first_group = self._group_claim
            if first_scope is not scope:
                raise exceptions.GroupScopeConflictError(
                    provider=self,
                    first_group=first_group,
                    first_scope=first_scope,
                    second_group=group_name,
                    second_scope=scope,
                )
            return
        if self._registered and self.scope is not scope:
            raise exceptions.ProviderScopeFrozenError(
                provider=self,
                group_name=group_name,
                current_scope=self.scope,
                new_scope=scope,
            )
        self._group_claim = (scope, group_name)

    @property
    def display_name(self) -> str:
        """Human-readable name for error messages and resolution steps: the bound type's, else the repr."""
        return self.bound_type.__name__ if self.bound_type else repr(self)

    @property
    def definition_site(self) -> str | None:
        """``module:line`` of the provider's declaration when known; None by default (no creator)."""
        return None

    def _resolution_step(self, scope: enum.IntEnum | None = None) -> exceptions.ResolutionStep:
        """Return this provider as a chain step at ``scope``, its own scope by default."""
        return exceptions.ResolutionStep(
            scope=self.scope if scope is None else scope, name=self.display_name, location=self.definition_site
        )

    def _get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:  # noqa: ARG002
        return {}

    def _redirect_target(self, container: "Container") -> "AbstractProvider[typing.Any] | None":  # noqa: ARG002
        """Return the provider this transparently forwards to, or None if resolution terminates here."""
        return None

    def _iter_validation_issues(self, container: "Container") -> typing.Iterable[Exception]:  # noqa: ARG002
        """Yield validation-time issues for this provider. Default: no issues."""
        return iter(())
