import dataclasses
import enum
import inspect
import typing
import warnings

from modern_di import exceptions, suggester, types
from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.context_provider import ContextProvider
from modern_di.types_parser import SignatureItem, parse_creator
from modern_di.wiring import WiringPlan, _Absent, absent_disposition


if typing.TYPE_CHECKING:
    from modern_di import Container
    from modern_di.registries.providers_registry import ProvidersRegistry


@dataclasses.dataclass(kw_only=True, slots=True)
class CacheSettings(typing.Generic[types.T_co]):
    clear_cache: bool = True
    finalizer: typing.Callable[[types.T_co], None | typing.Awaitable[None]] | None = None
    is_async_finalizer: bool = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self.is_async_finalizer = bool(self.finalizer) and inspect.iscoroutinefunction(self.finalizer)


class Factory(AbstractProvider[types.T_co]):
    __slots__ = ("_cached_definition_site", "_creator", "_kwargs", "_parsed_kwargs", "cache_settings")

    def __init__(  # noqa: C901, PLR0913
        self,
        creator: typing.Callable[..., types.T_co],
        *,
        scope: enum.IntEnum | types.UnsetType = types.UNSET,
        bound_type: type | None | types.UnsetType = types.UNSET,
        kwargs: dict[str, typing.Any] | None = None,
        cache: bool | CacheSettings[types.T_co] | None = None,
        cache_settings: CacheSettings[types.T_co] | None | types.UnsetType = types.UNSET,
        skip_creator_parsing: bool = False,
    ) -> None:
        if not isinstance(cache_settings, types.UnsetType):
            if cache is not None:
                msg = "pass only `cache`, not both `cache` and the deprecated `cache_settings`"
                raise TypeError(msg)
            if cache_settings is not None:
                warnings.warn(
                    "`cache_settings=` is deprecated; use `cache=` "
                    "(pass cache=True for defaults, or cache=CacheSettings(...) to tune). "
                    "It will be removed in a future release.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            cache = cache_settings
        if cache is True:
            resolved_cache: CacheSettings[types.T_co] | None = CacheSettings()
        elif cache:  # a CacheSettings instance
            resolved_cache = cache
        else:  # None or False
            resolved_cache = None
        if skip_creator_parsing:
            if bound_type is types.UNSET:
                warnings.warn(
                    "skip_creator_parsing=True without an explicit bound_type means this provider "
                    "cannot be resolved by type. Pass bound_type=MyClass if you need type resolution.",
                    UserWarning,
                    stacklevel=2,
                )
            parsed_type: type | None = None
            parsed_kwargs: dict[str, SignatureItem] = {}
        else:
            return_sig, parsed_kwargs = parse_creator(creator)
            parsed_type = return_sig.arg_type
            if kwargs:
                self._validate_kwargs_against_signature(creator, kwargs, parsed_kwargs)
            for param_name, item in parsed_kwargs.items():
                if item.raw_annotation is None or item.default is not types.UNSET or (kwargs and param_name in kwargs):
                    continue
                raise exceptions.UnsupportedCreatorParameterError(
                    creator=creator,
                    parameter_name=param_name,
                    reason=(
                        f"parameterized generic annotation {item.raw_annotation!r} cannot be resolved by type; "
                        f"pass the value via the kwargs parameter, give the parameter a default, "
                        f"or use skip_creator_parsing=True"
                    ),
                )
        self._parsed_kwargs = parsed_kwargs
        super().__init__(scope=scope, bound_type=parsed_type if isinstance(bound_type, types.UnsetType) else bound_type)
        self._creator = creator
        self.cache_settings = resolved_cache
        self._kwargs = kwargs
        self._cached_definition_site: str | None | types.UnsetType = types.UNSET

    @staticmethod
    def _validate_kwargs_against_signature(
        creator: typing.Callable[..., typing.Any],
        kwargs: dict[str, typing.Any],
        parsed_kwargs: dict[str, SignatureItem],
    ) -> None:
        try:
            sig = inspect.signature(creator)
        except (ValueError, TypeError):
            return
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            return
        known = set(parsed_kwargs)
        unknown = sorted(set(kwargs) - known)
        if not unknown:
            return
        raise exceptions.UnknownFactoryKwargError(
            creator=creator,
            unknown_keys=unknown,
            known_keys=sorted(known),
        )

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
        # The anchor machinery's contract is "never raise": even a pathological creator whose
        # attribute access blows up must degrade to an anchor-less step, not mask the real error.
        # Sole carve-out: a fresh RecursionError propagates (nothing memoized), because the runtime
        # cycle guard computes anchors inside its own RecursionError handler with the stack still
        # near-exhausted, and its retry ladder re-converts one frame up with more headroom.
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

    def _resolution_step(self) -> exceptions.ResolutionStep:
        return exceptions.ResolutionStep(scope=self.scope, name=self.display_name, location=self.definition_site)

    def _argument_resolution_error(
        self, *, arg_name: str, item: SignatureItem, registry: "ProvidersRegistry | None" = None
    ) -> exceptions.ArgumentResolutionError:
        # The context path passes no registry, so absent-context errors carry no suggestions.
        suggestions = (
            suggester.suggest(item.arg_type, registry) if registry is not None and item.arg_type is not None else []
        )
        return exceptions.ArgumentResolutionError(
            arg_name=arg_name,
            arg_type=item.arg_type,
            bound_type=self.bound_type or self._creator,
            suggestions=suggestions,
            member_types=item.args,
        )

    def _plan(self, container: "Container") -> WiringPlan:
        # The plan is memoized on the providers registry (shared by a container and every child), so a
        # deeper-scope factory builds it once per registry version, not once per child container. Passing
        # the build inputs to plan_for (rather than a closure) keeps the hot cache-hit path allocation-free.
        # Building runs outside the container lock — safe under the GIL since it's a deterministic function
        # of the registry as of the version it was built against (free-threaded/nogil caveat: planning/deferred.md).
        return container.providers_registry.plan_for(self, self._parsed_kwargs, self._kwargs)

    def _resolve_context_value(
        self, container: "Container", arg_name: str, provider: ContextProvider[typing.Any], item: SignatureItem
    ) -> typing.Any:  # noqa: ANN401
        """Resolve a context-backed parameter live. Returns ``types.UNSET`` to omit the kwarg.

        Absent value falls back to the creator default (omit), ``None`` (nullable), or raises
        ``ArgumentResolutionError`` (required).
        """
        override = container.overrides_registry.fetch_override(provider.provider_id)
        if override is not types.UNSET:
            return override
        value = provider.fetch_context_value(container)
        if value is not types.UNSET:
            return value
        disposition = absent_disposition(item)
        if disposition is _Absent.OMIT:
            return types.UNSET  # omit kwarg; creator default applies
        if disposition is _Absent.NULL:
            return None
        raise self._argument_resolution_error(arg_name=arg_name, item=item)

    def get_dependencies(self, container: "Container") -> dict[str, "AbstractProvider[typing.Any]"]:
        """Return parameter-name → dependency-provider mapping using only the providers registry.

        Pure lookup: no scope check, no cache touch, no context-value lookup. Used by
        Container.validate() to traverse the static graph.
        """
        return self._plan(container).edges

    def iter_validation_issues(self, container: "Container") -> typing.Iterable[Exception]:
        """Yield ArgumentResolutionError for parameters with no provider, no default, no static kwarg."""
        plan = self._plan(container)
        for name, item in plan.unwireable:
            yield self._argument_resolution_error(arg_name=name, item=item, registry=container.providers_registry)

    def _call_creator(self, resolved_kwargs: dict[str, typing.Any]) -> types.T_co:
        try:
            return self._creator(**resolved_kwargs)
        except TypeError as exc:
            # Argument-binding failures raise here with no inner traceback frame; a TypeError
            # raised inside the creator body must propagate unchanged, like ValueError/RuntimeError.
            if exc.__traceback__ is not None and exc.__traceback__.tb_next is not None:
                raise
            error = exceptions.CreatorCallError(creator=self._creator, original_error=exc)
            error.prepend_step(self._resolution_step())
            raise error from exc
