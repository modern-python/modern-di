import typing

from modern_di import errors, types
from modern_di.providers.abstract import AbstractProvider


class ProvidersRegistry:
    __slots__ = ("_providers",)

    def __init__(self) -> None:
        self._providers: dict[type, AbstractProvider[typing.Any]] = {}

    def find_provider(self, dependency_type: type[types.T]) -> AbstractProvider[types.T] | None:
        return self._providers.get(dependency_type)

    def add_providers(self, *args: AbstractProvider[typing.Any]) -> None:
        for provider in args:
            provider_type = provider.bound_type
            if not provider_type:
                continue

            if provider_type in self._providers:
                raise RuntimeError(errors.PROVIDER_DUPLICATE_TYPE_ERROR.format(provider_type=provider_type))

            self._providers[provider_type] = provider
