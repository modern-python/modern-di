import dataclasses
import enum
import inspect
import typing
import warnings

from modern_di import exceptions, suggester, types
from modern_di.providers.abstract import AbstractProvider
from modern_di.types_parser import ParsedCreator, SignatureItem, parse_creator
from modern_di.wiring import WiringPlan


if typing.TYPE_CHECKING:
    from modern_di import Container
    from modern_di.registries.providers_registry import ProvidersRegistry


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class CacheSettings(typing.Generic[types.T_contra]):
    clear_cache: bool = True
    finalizer: typing.Callable[[types.T_contra], typing.Awaitable[None] | None] | None = None
    _is_async_finalizer: bool = dataclasses.field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        is_async = bool(self.finalizer) and inspect.iscoroutinefunction(self.finalizer)
        object.__setattr__(self, "_is_async_finalizer", is_async)

    @staticmethod
    def _coerce(cache: "bool | CacheSettings[types.T]") -> "CacheSettings[types.T] | None":
        """Read a ``Factory``'s ``cache`` argument: ``True`` is the defaults, ``False`` is off."""
        if isinstance(cache, CacheSettings):
            return cache
        if cache is True:
            return CacheSettings()
        if cache is False:
            return None
        msg = (
            f"Factory cache= takes a bool or a CacheSettings; got {cache!r}. "
            "Pass cache=False, or leave it out, for an uncached factory."
        )
        raise TypeError(msg)


class Factory(AbstractProvider[types.T_co]):
    __slots__ = (
        "_cache_settings",
        "_cached_definition_site",
        "_creator",
        "_has_positional_only_gap",
        "_kwargs",
        "_params",
    )

    def __init__(  # noqa: PLR0913
        self,
        creator: typing.Callable[..., types.T_co],
        *,
        scope: enum.IntEnum | types.UnsetType = types.UNSET,
        bound_type: type | types.UnsetType | None = types.UNSET,
        kwargs: dict[str, typing.Any] | None = None,
        cache: bool | CacheSettings[types.T_co] = False,
        skip_creator_parsing: bool = False,
    ) -> None:
        parsed = self._parse_creator(
            creator, bound_type=bound_type, kwargs=kwargs, skip_creator_parsing=skip_creator_parsing
        )
        self._params = parsed.params
        self._has_positional_only_gap = parsed.has_positional_only_gap
        super().__init__(
            scope=scope,
            bound_type=parsed.return_type.arg_type if isinstance(bound_type, types.UnsetType) else bound_type,
        )
        self._creator = creator
        self._cache_settings: CacheSettings[typing.Any] | None = CacheSettings._coerce(cache)  # noqa: SLF001
        self._kwargs = kwargs
        self._cached_definition_site: str | types.UnsetType | None = types.UNSET

    @staticmethod
    def _parse_creator(
        creator: typing.Callable[..., typing.Any],
        *,
        bound_type: type | types.UnsetType | None,
        kwargs: dict[str, typing.Any] | None,
        skip_creator_parsing: bool,
    ) -> ParsedCreator:
        """Parse and check ``creator`` for ``__init__``; warnings point at the ``Factory(...)`` call."""
        if skip_creator_parsing:
            if bound_type is types.UNSET:
                warnings.warn(
                    "skip_creator_parsing=True without an explicit bound_type means this provider "
                    "cannot be resolved by type. Pass bound_type=MyClass if you need type resolution.",
                    UserWarning,
                    stacklevel=3,
                )
            return ParsedCreator(
                return_type=SignatureItem(), params={}, has_positional_only_gap=False, accepts_any_kwargs=True
            )
        parsed = parse_creator(creator)
        if kwargs:
            Factory._reject_unknown_kwargs(creator, kwargs, parsed)
        Factory._reject_unresolvable_generics(creator, kwargs, parsed)
        if parsed.return_type.member_types and bound_type is types.UNSET:
            members = " | ".join(getattr(t, "__name__", str(t)) for t in parsed.return_type.member_types)
            warnings.warn(
                f"The return annotation of {creator!r} is a union of {members}, so no bound_type can be "
                "inferred and this provider cannot be resolved by type. Pass bound_type=OneOfThem, or "
                "bound_type=None to silence this warning.",
                UserWarning,
                stacklevel=3,
            )
        return parsed

    @staticmethod
    def _reject_unknown_kwargs(
        creator: typing.Callable[..., typing.Any], kwargs: dict[str, typing.Any], parsed: ParsedCreator
    ) -> None:
        if parsed.accepts_any_kwargs:
            return
        known = set(parsed.params)
        unknown = sorted(set(kwargs) - known)
        if not unknown:
            return
        raise exceptions.UnknownFactoryKwargError(
            creator=creator,
            unknown_keys=unknown,
            known_keys=sorted(known),
        )

    @staticmethod
    def _reject_unresolvable_generics(
        creator: typing.Callable[..., typing.Any], kwargs: dict[str, typing.Any] | None, parsed: ParsedCreator
    ) -> None:
        for param_name, item in parsed.params.items():
            if item.raw_annotation is None or item.default is not types.UNSET or (kwargs and param_name in kwargs):
                continue
            raise exceptions.UnsupportedCreatorParameterError(
                creator=creator,
                parameter_name=param_name,
                reason=(
                    f"parameterized generic annotation {item.raw_annotation!r} cannot be resolved by type; "
                    "pass the value via the kwargs parameter or give the parameter a default"
                ),
            )

    @property
    def cache_settings(self) -> CacheSettings[typing.Any] | None:
        """The cache configuration, or ``None`` for an uncached factory."""
        return self._cache_settings

    def __repr__(self) -> str:
        return f"Factory(creator={self._creator!r}, scope={self.scope!r}, cached={self.cache_settings is not None})"

    @property
    def display_name(self) -> str:
        if self.bound_type:
            return self.bound_type.__name__
        return getattr(self._creator, "__name__", repr(self._creator))

    @property
    def definition_site(self) -> str | None:
        """The creator's declaration site as ``module:line``; None when undeterminable. Memoized."""
        if isinstance(self._cached_definition_site, types.UnsetType):
            self._cached_definition_site = self._compute_definition_site()
        return self._cached_definition_site

    def _compute_definition_site(self) -> str | None:
        """Compute the creator's ``module:line``, degrading to None rather than masking a real error.

        A ``RecursionError`` is the carve-out: the runtime cycle guard computes anchors inside
        its own handler and retries one frame up.
        """
        try:
            module = getattr(self._creator, "__module__", None)
            if module is None:
                return None
            code = getattr(self._creator, "__code__", None)
            if code is not None:
                return f"{module}:{code.co_firstlineno}"
            _, lineno = inspect.getsourcelines(self._creator)
        except RecursionError:
            raise
        except Exception:  # noqa: BLE001
            return None
        return f"{module}:{lineno}"

    def _argument_resolution_error(
        self, *, arg_name: str, item: SignatureItem, registry: "ProvidersRegistry"
    ) -> exceptions.ArgumentResolutionError:
        suggestions = suggester.suggest(item.arg_type, registry) if item.arg_type is not None else []
        return exceptions.ArgumentResolutionError(
            parameter_name=arg_name,
            parameter_type=item.arg_type,
            bound_type=self.bound_type,
            creator=self._creator,
            suggestions=suggestions,
            member_types=item.member_types,
        )

    def _wiring_plan(self, registry: "ProvidersRegistry") -> WiringPlan:
        """Return this factory's wiring plan, memoized on the tree-wide providers registry."""
        return registry.plan_for(self)

    def _can_call_positionally(self, plan: WiringPlan) -> bool:
        """Whether this creator can be called positionally under `plan`.

        True when every parsed parameter is a positional-or-keyword provider dependency, in signature
        order, with nothing omitted, added, keyword-only or positional-only.
        """
        if plan.static_kwargs:
            return False
        names = tuple(self._params)
        if tuple(plan.provider_kwargs) != names:
            return False
        if any(item.is_keyword_only for item in self._params.values()):
            return False
        return not (names and self._has_positional_only_gap)

    def _get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:
        """Return parameter name → dependency provider: a pure registry lookup, no scope or cache touched."""
        return self._wiring_plan(container._providers_registry).provider_kwargs  # noqa: SLF001

    def _iter_validation_issues(self, container: "Container") -> typing.Iterable[Exception]:
        """Yield ArgumentResolutionError for parameters with no provider, no default, no static kwarg."""
        registry = container._providers_registry  # noqa: SLF001
        plan = self._wiring_plan(registry)
        for name, item in plan.unwireable:
            yield self._argument_resolution_error(arg_name=name, item=item, registry=registry)
