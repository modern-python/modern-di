import dataclasses
import typing
import warnings

from modern_di.providers.abstract import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class ProvidersRegistry:
    providers_by_name: dict[str, AbstractProvider[typing.Any]] = dataclasses.field(init=False, default_factory=dict)
    providers_by_type: dict[type, AbstractProvider[typing.Any]] = dataclasses.field(init=False, default_factory=dict)

    def find_provider(
        self, dependency_name: str | None = None, dependency_type: type[T_co] | None = None
    ) -> AbstractProvider[T_co] | None:
        if dependency_name and (provider := self.providers_by_name.get(dependency_name)):
            return provider

        if dependency_type and (provider := self.providers_by_type.get(dependency_type)):
            return provider

        return None

    def add_providers(self, **kwargs: AbstractProvider[typing.Any]) -> None:
        for provider_name, provider in kwargs.items():
            if provider_name in self.providers_by_name:
                warnings.warn(
                    f"Provider is duplicated by name {provider_name}. Choose unique name if you want resolving by name",
                    RuntimeWarning,
                    stacklevel=2,
                )
                del self.providers_by_name[provider_name]
            else:
                self.providers_by_name[provider_name] = provider

            provider_type = provider.bound_type
            if not provider_type:
                continue

            if provider_type in self.providers_by_type:
                warnings.warn(
                    f"Provider is duplicated by type {provider_type}. "
                    f"Bind provider to unique type if you want resolving by type",
                    RuntimeWarning,
                    stacklevel=2,
                )
                del self.providers_by_type[provider_type]
                continue

            self.providers_by_type[provider_type] = provider
