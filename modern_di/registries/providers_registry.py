import typing

from modern_di import types
from modern_di.providers.abstract import AbstractProvider


class ProvidersRegistry:
    __slots__ = ("_providers",)

    def __init__(self) -> None:
        self._providers: dict[tuple[type, str | None], AbstractProvider[typing.Any]] = {}

    def find_provider(
        self, dependency_type: type[types.T], qualifier: str | None = None
    ) -> AbstractProvider[types.T] | None:
        return self._providers.get((dependency_type, qualifier))

    def add_providers(self, *args: AbstractProvider[typing.Any]) -> None:
        for provider in args:
            provider_type = provider.bound_type
            if not provider_type:
                continue

            found_provider = self.find_provider(provider_type, provider.qualifier)  # type: ignore

            if found_provider:
                msg = f"Provider is duplicated by type {provider_type} and has the same qualifier {provider.qualifier}"
                raise RuntimeError(msg)

            self._providers[(provider_type, provider.qualifier)] = provider
