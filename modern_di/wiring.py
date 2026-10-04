"""Kwarg-wiring decision for Factory providers: a pure function of the signature and the registry."""

import dataclasses
import typing

from modern_di.providers.abstract import AbstractProvider
from modern_di.types import UNSET
from modern_di.types_parser import SignatureItem


if typing.TYPE_CHECKING:
    from modern_di.providers.factory import Factory
    from modern_di.registries.providers_registry import ProvidersRegistry


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

    ``pure_provider`` means no static kwargs, so the call can be built from ``provider_kwargs``
    alone. ``unwireable`` holds records rather than pre-built exceptions: a plan is memoized, and
    ``prepend_step`` mutates the error it is called on.
    """

    provider_kwargs: dict[str, "AbstractProvider[typing.Any]"]
    static_kwargs: dict[str, typing.Any]
    unwireable: "list[tuple[str, SignatureItem]]"
    pure_provider: bool

    @property
    def edges(self) -> dict[str, "AbstractProvider[typing.Any]"]:
        """Every provider this plan resolves: the bucket ``resolve()`` reads."""
        return self.provider_kwargs

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
        provider_kwargs, static_kwargs, unwireable = cls._wire_by_type(
            parsed_kwargs=parsed_kwargs,
            kwargs=kwargs,
            registry=registry,
            owner=owner,
        )

        for name, value in (kwargs or {}).items():
            if isinstance(value, AbstractProvider):
                provider_kwargs[name] = value
            else:
                static_kwargs[name] = value

        return cls(
            provider_kwargs=provider_kwargs,
            static_kwargs=static_kwargs,
            unwireable=unwireable,
            pure_provider=not static_kwargs,
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
        "list[tuple[str, SignatureItem]]",
    ]:
        """Bucket each parsed parameter by type; a name in ``kwargs={...}`` is left to the overlay.

        A parameter with no provider is omitted when it has a default, gets ``None`` when nullable,
        and is unwireable otherwise.
        """
        provider_kwargs: dict[str, AbstractProvider[typing.Any]] = {}
        static_kwargs: dict[str, typing.Any] = {}
        unwireable: list[tuple[str, SignatureItem]] = []

        for name, item in parsed_kwargs.items():
            if kwargs and name in kwargs:
                continue
            provider = find_dep_provider(registry, owner, item)
            if provider is not None:
                provider_kwargs[name] = provider
            elif item.default is not UNSET:
                continue
            elif item.is_nullable:
                static_kwargs[name] = None
            else:
                unwireable.append((name, item))

        return provider_kwargs, static_kwargs, unwireable
