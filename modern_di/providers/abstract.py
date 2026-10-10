import enum
import itertools
import typing

from modern_di import exceptions, types
from modern_di.scope import Scope


_provider_id_counter = itertools.count()


class AbstractProvider(typing.Generic[types.T_co]):
    """Shared base of ``Factory``, ``Alias``, ``ContextProvider`` and ``container_provider``.

    It appears in signatures that accept any provider. The provider set is closed: subclassing it,
    or any provider, outside modern-di raises ``TypeError``.
    """

    __slots__ = ("_bound_type", "_explicit_scope", "_group_claim", "_provider_id", "_registered")

    _takes_group_scope: typing.ClassVar[bool] = True
    """Whether a Group-level default scope applies. False when the effective scope is derived."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        if cls.__module__.partition(".")[0] != "modern_di":
            msg = (
                f"{cls.__qualname__} subclasses a modern-di provider. The provider set is closed, so a "
                "subclass would not resolve. Compose behavior in a creator function or an Alias instead."
            )
            raise TypeError(msg)
        super().__init_subclass__(**kwargs)

    def __init__(
        self,
        *,
        scope: enum.IntEnum | types.UnsetType,
        bound_type: type | types.UnsetType | None,
        inferred_bound_type: type | None = None,
    ) -> None:
        """Set the shared state; an unset ``bound_type`` falls back to ``inferred_bound_type``."""
        self._explicit_scope: enum.IntEnum | None = scope if isinstance(scope, enum.IntEnum) else None
        self._group_claim: tuple[enum.IntEnum, str] | None = None
        self._registered = False
        self._bound_type = inferred_bound_type if isinstance(bound_type, types.UnsetType) else bound_type
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
        """The declared scope: the provider's own ``scope=``, else a Group default, else ``Scope.APP``.

        A redirect such as ``Alias`` resolves at its source's scope instead.
        """
        if self._explicit_scope is not None:
            return self._explicit_scope
        if self._group_claim is not None:
            return self._group_claim[0]
        return Scope.APP

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
