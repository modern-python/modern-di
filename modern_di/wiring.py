"""Kwarg-wiring decision for Factory providers: a pure function of the signature and the registry."""

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
    """Disposition for a parameter with no matching provider: default, then nullable, then unwirable."""
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
    """Look up a dependency provider for *item*, excluding *owner*: ``arg_type``, else a union member."""
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
    """Immutable result of partitioning a creator's parameters into wiring buckets.

    ``pure_provider`` means no static and no context kwargs, so the call can be built from
    ``provider_kwargs`` alone. ``unwireable`` holds records rather than pre-built exceptions: a
    plan is memoized, and ``prepend_step`` mutates the error it is called on.
    """

    provider_kwargs: dict[str, "AbstractProvider[typing.Any]"]
    static_kwargs: dict[str, typing.Any]
    context_kwargs: dict[str, "tuple[ContextProvider[typing.Any], SignatureItem]"]
    unwireable: "list[tuple[str, SignatureItem]]"
    pure_provider: bool

    @property
    def edges(self) -> dict[str, "AbstractProvider[typing.Any]"]:
        """Every provider this plan resolves — derived from the buckets ``resolve()`` reads."""
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
        """Partition *parsed_kwargs* by type, then overlay ``kwargs={...}``. Never raises."""
        provider_kwargs, static_kwargs, context_kwargs, unwireable = cls._wire_by_type(
            parsed_kwargs=parsed_kwargs,
            kwargs=kwargs,
            registry=registry,
            owner=owner,
        )

        if kwargs:
            cls._apply_overlay(
                kwargs=kwargs,
                parsed_kwargs=parsed_kwargs,
                provider_kwargs=provider_kwargs,
                static_kwargs=static_kwargs,
                context_kwargs=context_kwargs,
            )

        return cls(
            provider_kwargs=provider_kwargs,
            static_kwargs=static_kwargs,
            context_kwargs=context_kwargs,
            unwireable=unwireable,
            pure_provider=not static_kwargs and not context_kwargs,
        )

    @staticmethod
    def _wire_by_type(
        *,
        parsed_kwargs: dict[str, SignatureItem],
        kwargs: dict[str, typing.Any] | None,
        registry: "ProvidersRegistry",
        owner: "Factory[typing.Any]",
    ) -> tuple[
        dict[str, "AbstractProvider[typing.Any]"],
        dict[str, typing.Any],
        dict[str, "tuple[ContextProvider[typing.Any], SignatureItem]"],
        "list[tuple[str, SignatureItem]]",
    ]:
        """Bucket each parsed parameter by type; a name in ``kwargs={...}`` is left to the overlay."""
        provider_kwargs: dict[str, AbstractProvider[typing.Any]] = {}
        static_kwargs: dict[str, typing.Any] = {}
        context_kwargs: dict[str, tuple[ContextProvider[typing.Any], SignatureItem]] = {}
        unwireable: list[tuple[str, SignatureItem]] = []

        for name, item in parsed_kwargs.items():
            if kwargs and name in kwargs:
                continue

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
            unwireable.append((name, item))

        return provider_kwargs, static_kwargs, context_kwargs, unwireable

    @staticmethod
    def _apply_overlay(
        *,
        kwargs: dict[str, typing.Any],
        parsed_kwargs: dict[str, SignatureItem],
        provider_kwargs: dict[str, "AbstractProvider[typing.Any]"],
        static_kwargs: dict[str, typing.Any],
        context_kwargs: dict[str, "tuple[ContextProvider[typing.Any], SignatureItem]"],
    ) -> None:
        """Bucket each explicit ``kwargs={...}`` entry into the buckets the by-type pass built.

        A ``ContextProvider`` carries its ``SignatureItem`` so an unset value honors the default
        or nullable; with no parsed item it stays a plain provider and resolves directly.
        """
        for name, value in kwargs.items():
            item = parsed_kwargs.get(name)
            if isinstance(value, ContextProvider) and item is not None:
                context_kwargs[name] = (value, item)
            elif isinstance(value, AbstractProvider):
                provider_kwargs[name] = value
            else:
                static_kwargs[name] = value
