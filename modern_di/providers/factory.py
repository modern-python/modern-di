import dataclasses
import enum
import inspect
import typing
import warnings

from modern_di import exceptions, types
from modern_di.providers.abstract import AbstractProvider
from modern_di.types_parser import ParsedCreator, SignatureItem, parse_creator
from modern_di.wiring import WiringPlan


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class CacheSettings(typing.Generic[types.T_contra]):
    """How a cached ``Factory`` keeps and releases its instance.

    ``finalizer`` runs on the instance when its container closes; it may be sync or async. With
    ``clear_cache=True``, the default, the instance is dropped at close and rebuilt on the next
    resolve after reopening. With ``clear_cache=False`` the same instance survives close and reopen,
    and its finalizer runs only once.
    """

    clear_cache: bool = True
    finalizer: typing.Callable[[types.T_contra], object] | None = None
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
    """Provider that calls ``creator`` to build its value, wiring its parameters from the container.

    Each parameter is resolved by its annotated type unless ``kwargs`` gives it a value or a
    provider. The bound type defaults to the creator's return annotation; ``bound_type=None`` makes
    the provider resolvable by reference only. ``cache=True`` or a ``CacheSettings`` builds the value
    once per container at the provider's scope. ``skip_creator_parsing=True`` turns off wiring, so
    every required argument must come from ``kwargs``.
    """

    __slots__ = (
        "_cache_settings",
        "_cached_definition_site",
        "_creator",
        "_kwargs",
        "_params",
        "_positional_names",
    )

    def __init__(  # noqa: PLR0913
        self,
        creator: typing.Callable[..., types.T_co],
        *,
        scope: enum.IntEnum | types.UnsetType = types.UNSET,
        bound_type: typing.Any = types.UNSET,  # noqa: ANN401
        kwargs: dict[str, typing.Any] | None = None,
        cache: bool | CacheSettings[types.T_co] = False,
        skip_creator_parsing: bool = False,
    ) -> None:
        parsed = self._parse_creator(
            creator, bound_type=bound_type, kwargs=kwargs, skip_creator_parsing=skip_creator_parsing
        )
        self._params = parsed.params
        names = tuple(parsed.params)
        self._positional_names: tuple[str, ...] | None = names
        if (names and parsed.has_positional_only_gap) or any(item.is_keyword_only for item in parsed.params.values()):
            self._positional_names = None
        super().__init__(scope=scope, bound_type=bound_type, inferred_bound_type=parsed.return_type.arg_type)
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
            if (
                item.unresolvable_generic is None
                or item.default is not types.UNSET
                or (kwargs and param_name in kwargs)
            ):
                continue
            raise exceptions.UnsupportedCreatorParameterError(
                creator=creator,
                parameter_name=param_name,
                reason=(
                    f"parameterized generic annotation {item.unresolvable_generic!r} cannot be resolved by type; "
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

    def _can_call_positionally(self, plan: WiringPlan) -> bool:
        """Whether this creator can be called positionally under `plan`.

        True when every parsed parameter is a positional-or-keyword provider dependency, in signature
        order, with nothing omitted, added, keyword-only or positional-only.
        """
        if plan.static_kwargs or self._positional_names is None:
            return False
        return tuple(plan.provider_kwargs) == self._positional_names
