"""Kwarg-wiring decision for Factory providers.

``WiringPlan`` partitions a creator's parsed parameters into provider
lookups, static values, and context lookups. It is a pure function of its
inputs — no cache, no scope, no live context — so it is exercisable without
a Container.
"""

import dataclasses
import enum
import typing

from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.context_provider import ContextProvider
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
    """Decide the disposition for a parameter with no matching provider.

    Precedence: default before nullable before unwirable.
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

    Prefers ``arg_type``; falls back to the first matching type in ``args``
    (union members).
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
        unwireable:       UNWIRABLE parameters as (param-name, SignatureItem)
                          records rather than pre-built exceptions, so a fresh
                          ``ArgumentResolutionError`` can be constructed at
                          each raise/yield site without ``prepend_step``
                          mutations compounding across resolves of the same
                          memoized plan.

    """

    provider_kwargs: dict[str, "AbstractProvider[typing.Any]"]
    static_kwargs: dict[str, typing.Any]
    context_kwargs: dict[str, "tuple[ContextProvider[typing.Any], SignatureItem]"]
    unwireable: "list[tuple[str, SignatureItem]]"

    @property
    def edges(self) -> dict[str, "AbstractProvider[typing.Any]"]:
        """Every provider this plan resolves — the graph ``validate()`` traverses.

        Derived from the buckets ``resolve()`` reads, so the validated graph cannot
        drift from the resolved one. Providers supplied via ``kwargs={...}`` are edges
        like any other: only the *declaration* differs, not the dependency.
        """
        return {
            **self.provider_kwargs,
            **{name: provider for name, (provider, _item) in self.context_kwargs.items()},
        }

    @classmethod
    def build(
        cls,
        *,
        parsed_kwargs: dict[str, SignatureItem],
        kwargs: dict[str, typing.Any] | None,
        registry: "ProvidersRegistry",
        owner: "Factory[typing.Any]",
    ) -> "WiringPlan":
        """Partition *parsed_kwargs* into wiring buckets. Never raises."""
        provider_kwargs: dict[str, AbstractProvider[typing.Any]] = {}
        static_kwargs: dict[str, typing.Any] = {}
        context_kwargs: dict[str, tuple[ContextProvider[typing.Any], SignatureItem]] = {}
        unwireable: list[tuple[str, SignatureItem]] = []

        for name, item in parsed_kwargs.items():
            if kwargs and name in kwargs:
                continue  # supplied as a static kwarg below

            provider = find_dep_provider(registry, owner, item)
            if provider is not None:
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

        if kwargs:  # static overlay
            for name, value in kwargs.items():
                if isinstance(value, AbstractProvider):
                    provider_kwargs[name] = value
                else:
                    static_kwargs[name] = value

        return cls(
            provider_kwargs=provider_kwargs,
            static_kwargs=static_kwargs,
            context_kwargs=context_kwargs,
            unwireable=unwireable,
        )
