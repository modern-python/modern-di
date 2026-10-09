"""Kwarg-wiring decision for Factory providers: a pure function of the signature and the registry."""

import dataclasses
import typing

from modern_di import exceptions, suggester
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
    """Look up a provider for the first registered union member of *item*, excluding *owner*."""
    for x in item.member_types:
        provider = registry.find_provider(x)
        if provider is not None and provider is not owner:
            return provider
    return None


@dataclasses.dataclass(frozen=True, slots=True)
class WiringPlan:
    """Immutable result of partitioning a creator's parameters into wiring buckets.

    ``provider_kwargs`` holds every provider the plan resolves, so it is also the edge set the
    dependency graph walks. ``unwireable`` holds records rather than pre-built exceptions: a plan
    is memoized, and ``_prepend_step`` mutates the error it is called on.
    """

    provider_kwargs: dict[str, "AbstractProvider[typing.Any]"]
    static_kwargs: dict[str, typing.Any]
    unwireable: "list[tuple[str, SignatureItem]]"

    @classmethod
    def build(cls, owner: "Factory[typing.Any]", *, registry: "ProvidersRegistry") -> "WiringPlan":
        """Bucket each parameter by type, then overlay ``owner``'s ``kwargs={...}``. Never raises.

        A parameter named in ``kwargs={...}`` is left to the overlay. One with no provider is omitted
        when it has a default, gets ``None`` when nullable, and is unwireable otherwise.
        """
        kwargs = owner._kwargs  # noqa: SLF001
        provider_kwargs: dict[str, AbstractProvider[typing.Any]] = {}
        static_kwargs: dict[str, typing.Any] = {}
        unwireable: list[tuple[str, SignatureItem]] = []
        for name, item in owner._params.items():  # noqa: SLF001
            if kwargs and name in kwargs:
                continue
            if item.arg_type is not None:
                provider = registry.find_provider(item.arg_type)
                if provider is owner:
                    provider = None
            else:
                provider = find_dep_provider(registry, owner, item)
            if provider is not None:
                provider_kwargs[name] = provider
            elif item.default is not UNSET:
                continue
            elif item.is_nullable:
                static_kwargs[name] = None
            else:
                unwireable.append((name, item))

        if kwargs:
            _overlay(kwargs, provider_kwargs, static_kwargs)
        return cls(provider_kwargs, static_kwargs, unwireable)


def _overlay(
    kwargs: dict[str, typing.Any],
    provider_kwargs: dict[str, "AbstractProvider[typing.Any]"],
    static_kwargs: dict[str, typing.Any],
) -> None:
    """Sort ``kwargs={...}`` into provider and static arguments, over whatever was wired by type."""
    for name, value in kwargs.items():
        if isinstance(value, AbstractProvider):
            provider_kwargs[name] = value
        else:
            static_kwargs[name] = value


def argument_resolution_error(
    factory: "Factory[typing.Any]", arg_name: str, item: SignatureItem, registry: "ProvidersRegistry"
) -> exceptions.ArgumentResolutionError:
    """Build the error for a ``factory`` parameter that no provider, default or static kwarg covers."""
    return exceptions.ArgumentResolutionError(
        parameter_name=arg_name,
        parameter_type=item.arg_type,
        bound_type=factory.bound_type,
        creator=factory._creator,  # noqa: SLF001
        suggestions=suggester.suggest(item.arg_type, registry) if item.arg_type is not None else [],
        member_types=item.member_types,
    )
