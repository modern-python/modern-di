import collections
import typing
import warnings

from modern_di import types
from modern_di.providers.abstract import AbstractProvider


class ProvidersRegistry:
    __slots__ = (
        "_by_name",
        "_by_type",
        "_overrides_by_name",
        "_overrides_by_type",
        "_providers_by_name",
        "_providers_by_type",
    )

    def __init__(self) -> None:
        self._providers_by_name: dict[str, AbstractProvider[typing.Any]] = {}
        self._providers_by_type: dict[type, AbstractProvider[typing.Any]] = {}
        self._overrides_by_name: dict[str, AbstractProvider[typing.Any]] = {}
        self._overrides_by_type: dict[type, AbstractProvider[typing.Any]] = {}

        self._by_name = collections.ChainMap(self._overrides_by_name, self._providers_by_name)
        self._by_type = collections.ChainMap(self._overrides_by_type, self._providers_by_type)

    def find_provider(
        self, dependency_name: str | None = None, dependency_type: type[types.T_co] | None = None
    ) -> AbstractProvider[types.T_co] | None:
        if dependency_name and (provider := self._by_name.get(dependency_name)):
            return provider

        if dependency_type and (provider := self._by_type.get(dependency_type)):
            return provider

        return None

    def add_providers(self, **kwargs: AbstractProvider[typing.Any]) -> None:
        for provider_name, provider in kwargs.items():
            if provider_name in self._providers_by_name:
                warnings.warn(
                    f"Provider is duplicated by name {provider_name}",
                    RuntimeWarning,
                    stacklevel=2,
                )
            self._providers_by_name[provider_name] = provider

            provider_type = provider.bound_type
            if not provider_type:
                continue

            if provider_type in self._providers_by_type:
                warnings.warn(
                    f"Provider is duplicated by type {provider_type}",
                    RuntimeWarning,
                    stacklevel=2,
                )

            self._providers_by_type[provider_type] = provider

    def override_provider(
        self,
        *,
        dependency_name: str | None = None,
        dependency_type: type[types.T_co] | None = None,
        new_provider: AbstractProvider[typing.Any],
    ) -> None:
        if dependency_name:
            self._overrides_by_name[dependency_name] = new_provider
        if dependency_type:
            self._overrides_by_type[dependency_type] = new_provider

    def reset_override(
        self, *, dependency_name: str | None = None, dependency_type: type[types.T_co] | None = None
    ) -> None:
        if dependency_name:
            self._overrides_by_name.pop(dependency_name, None)
        if dependency_type:
            self._overrides_by_type.pop(dependency_type, None)
        if not dependency_name and not dependency_type:
            self._overrides_by_name.clear()
            self._overrides_by_type.clear()
