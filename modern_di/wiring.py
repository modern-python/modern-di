"""Kwarg-wiring decision for Factory providers.

``WiringPlan`` is the single authoritative place where a creator's parsed
parameters are partitioned into provider lookups, static values, and context
lookups.  It is a pure function of its inputs — no cache, no scope, no live
context — so it is exercisable without a Container.

``absent_disposition`` is the single copy of the absent-value table:
    default is not UNSET  → OMIT (creator default applies)
    is_nullable           → NULL (inject None)
    else                  → UNWIRABLE (required, no provider)
"""

import dataclasses
import enum
import typing

from modern_di.providers import ContextProvider
from modern_di.providers.abstract import AbstractProvider
from modern_di.types import UNSET
from modern_di.types_parser import SignatureItem


if typing.TYPE_CHECKING:
    from modern_di.providers.factory import Factory
    from modern_di.registries.providers_registry import ProvidersRegistry


class _Absent(enum.Enum):
    OMIT = enum.auto()  # parameter omitted; creator default applies
    NULL = enum.auto()  # inject None (annotation was nullable)
    UNWIRABLE = enum.auto()  # required, no provider, no default → error


def absent_disposition(item: SignatureItem) -> _Absent:
    """Single copy of the absent-value table.

    Precedence: default before nullable before unwirable — matches today's
    ``_compile_kwargs`` order exactly.
    """
    if item.default is not UNSET:
        return _Absent.OMIT
    if item.is_nullable:
        return _Absent.NULL
    return _Absent.UNWIRABLE


def find_dep_provider(
    registry: "ProvidersRegistry",
    owner: "Factory[typing.Any]",
    item: SignatureItem,
) -> "AbstractProvider[typing.Any] | None":
    """Look up a dependency provider for *item* in *registry*, excluding *owner* itself.

    Mirrors ``Factory._find_dep_provider`` exactly: prefers ``arg_type``,
    falls back to the first matching type in ``args`` (union members).
    """
    if item.arg_type is not None:
        provider = registry.find_provider(item.arg_type)
        if provider is owner:
            return None
        return provider
    for x in item.args:
        provider = registry.find_provider(x)
        if provider is not None and provider is not owner:
            return provider
    return None


@dataclasses.dataclass(frozen=True, slots=True)
class WiringPlan:
    """Immutable result of partitioning a creator's parameters.

    Attributes:
        provider_kwargs:  name → provider resolved live each resolve call.
        static_kwargs:    name → literal value (including nullable-None).
        context_kwargs:   name → (ContextProvider, SignatureItem) looked up live.
        dependencies:     type-matched providers only (regular + context),
                          excluding providers supplied via ``kwargs={...}``.
                          Used by ``validate()``'s graph traversal.
        unwireable:       UNWIRABLE parameters as (param-name, SignatureItem)
                          records; ``build`` never raises. Consumers construct
                          fresh ``ArgumentResolutionError`` instances at
                          raise/yield time so that ``prepend_step`` mutations
                          do not compound across repeated resolves of the same
                          memoized plan.

    """

    provider_kwargs: dict[str, "AbstractProvider[typing.Any]"]
    static_kwargs: dict[str, typing.Any]
    context_kwargs: dict[str, "tuple[ContextProvider[typing.Any], SignatureItem]"]
    dependencies: dict[str, "AbstractProvider[typing.Any]"]
    unwireable: "list[tuple[str, SignatureItem]]"

    @classmethod
    def build(
        cls,
        *,
        parsed_kwargs: dict[str, SignatureItem],
        kwargs: dict[str, typing.Any] | None,
        registry: "ProvidersRegistry",
        owner: "Factory[typing.Any]",
    ) -> "WiringPlan":
        """Partition *parsed_kwargs* into wiring buckets.

        Pure function of its arguments — no cache, no scope, no live context —
        runnable outside the container lock (GIL-determinism argument preserved
        from ``_compile_kwargs``; free-threaded/nogil caveat tracked in
        planning/deferred.md).

        The plan never raises; unwireable parameters are recorded in
        ``unwireable`` as raw (name, SignatureItem) records — NOT pre-built
        exceptions — so that consumers can construct a fresh
        ``ArgumentResolutionError`` at each raise/yield site without risk of
        ``prepend_step`` mutations compounding across repeated resolves.
        """
        provider_kwargs: dict[str, AbstractProvider[typing.Any]] = {}
        static_kwargs: dict[str, typing.Any] = {}
        context_kwargs: dict[str, tuple[ContextProvider[typing.Any], SignatureItem]] = {}
        dependencies: dict[str, AbstractProvider[typing.Any]] = {}
        unwireable: list[tuple[str, SignatureItem]] = []

        for name, item in parsed_kwargs.items():
            if kwargs and name in kwargs:
                continue  # supplied as a static kwarg below

            provider = find_dep_provider(registry, owner, item)
            if provider is not None:
                dependencies[name] = provider  # validate-visible (type-matched only)
                if isinstance(provider, ContextProvider):
                    context_kwargs[name] = (provider, item)
                else:
                    provider_kwargs[name] = provider
                continue

            disposition = absent_disposition(item)
            if disposition is _Absent.OMIT:
                continue
            if disposition is _Absent.NULL:
                static_kwargs[name] = None
                continue
            # UNWIRABLE: record the (name, item) pair but do not raise
            unwireable.append((name, item))

        if kwargs:  # static overlay — NOT added to `dependencies`
            for name, value in kwargs.items():
                if isinstance(value, AbstractProvider):
                    provider_kwargs[name] = value
                else:
                    static_kwargs[name] = value

        return cls(
            provider_kwargs=provider_kwargs,
            static_kwargs=static_kwargs,
            context_kwargs=context_kwargs,
            dependencies=dependencies,
            unwireable=unwireable,
        )
