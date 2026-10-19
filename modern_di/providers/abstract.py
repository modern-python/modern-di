import enum
import itertools
import sys
import typing

from modern_di import exceptions, types
from modern_di.scope import Scope


_provider_id_counter = itertools.count()


class AbstractProvider(typing.Generic[types.T_co]):
    """Shared base of ``Factory``, ``Alias``, ``ContextProvider`` and ``container_provider``.

    It appears in signatures that accept any provider. The provider set is closed: subclassing it,
    or any provider, outside modern-di raises ``TypeError``.
    """

    __slots__ = (
        "_bound_type",
        "_call_line",
        "_call_module",
        "_declared_as",
        "_explicit_scope",
        "_group_claim",
        "_provider_id",
        "_registered",
    )

    _takes_group_scope: typing.ClassVar[bool] = True
    """Whether a Group-level default scope applies. False when the effective scope comes from another provider."""

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
        call_depth: int = 2,
    ) -> None:
        """Set the shared state; an unset ``bound_type`` falls back to ``inferred_bound_type``.

        ``call_depth`` is the frame, counted from here, of the user code that built the provider.
        """
        self._explicit_scope: enum.IntEnum | None = scope if isinstance(scope, enum.IntEnum) else None
        self._group_claim: tuple[enum.IntEnum, str] | None = None
        self._registered = False
        self._bound_type = inferred_bound_type if isinstance(bound_type, types.UnsetType) else bound_type
        self._provider_id = next(_provider_id_counter)
        self._declared_as: str | None = None
        caller = sys._getframe(call_depth)  # noqa: SLF001
        self._call_module: str | None = caller.f_globals.get("__name__")
        self._call_line = caller.f_lineno

    def __set_name__(self, owner: type, name: str) -> None:
        if self._declared_as is None:
            self._declared_as = f"{owner.__name__}.{name}"

    @property
    def bound_type(self) -> type | None:
        """The type this provider is registered under, or ``None`` when it resolves by reference only."""
        return self._bound_type

    @property
    def _call_site(self) -> str | None:
        """``module:line`` of the call that built this provider; None when the module is unknown."""
        return None if self._call_module is None else f"{self._call_module}:{self._call_line}"

    @property
    def provider_id(self) -> int:
        """A process-unique id."""
        return self._provider_id

    @property
    def scope(self) -> enum.IntEnum:
        """The declared scope: the provider's own ``scope=``, else a Group default, else ``Scope.APP``.

        For a redirect such as ``Alias`` this is a ``Scope.APP`` placeholder, not the effective scope: an
        alias resolves at its source's scope.
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
        return self.bound_type.__name__ if self.bound_type is not None else repr(self)

    @property
    def definition_site(self) -> str | None:
        """``module:line`` of the provider's declaration when known; None by default (no creator)."""
        return None

    def derive(self, fn: typing.Callable[[types.T_co], types.T], /) -> "AbstractProvider[types.T]":
        """Return a provider of ``fn(value)``, where ``value`` is what this provider resolves to.

        The derived provider is never cached and has no scope of its own: it resolves at this
        provider's scope, so it is valid in ``kwargs`` of any group, and an override of this provider
        reaches it. It is not registered under any type. An exception raised by ``fn`` propagates
        unchanged, with a note naming the derived provider.
        """
        return _Derived(self, fn)


class _Derived(AbstractProvider[types.T_co]):
    __slots__ = ("_fn", "_source")

    _takes_group_scope = False

    def __init__(self, source: AbstractProvider[typing.Any], fn: typing.Callable[[typing.Any], types.T_co]) -> None:
        super().__init__(scope=types.UNSET, bound_type=None, call_depth=3)
        self._source = source
        self._fn = fn

    def __repr__(self) -> str:
        return f"{self.display_name}({self._fn!r})"

    @property
    def display_name(self) -> str:
        return f"{self._source.display_name}.derive"

    @property
    def definition_site(self) -> str | None:
        """``fn``'s declaration site as ``module:line``; else the ``derive`` call site."""
        module = getattr(self._fn, "__module__", None)
        code = getattr(self._fn, "__code__", None)
        if module is None or code is None:
            return self._call_site
        return f"{module}:{code.co_firstlineno}"
