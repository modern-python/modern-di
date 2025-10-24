import dataclasses
import typing
import warnings

from modern_di.providers.abstract import AbstractProvider


T_co = typing.TypeVar("T_co", covariant=True)


@dataclasses.dataclass(slots=True, frozen=True)
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
        if duplicates_by_name := set(self.providers_by_name.keys()) & set(kwargs.keys()):
            warnings.warn(f"Duplicated by name providers {duplicates_by_name}", RuntimeWarning, stacklevel=2)

        self.providers_by_name.update(kwargs)

        if duplicates_by_type := set(self.providers_by_type.keys()) & {
            x.bound_type for x in kwargs.values() if x.bound_type
        }:
            warnings.warn(f"Duplicated by type providers {duplicates_by_type}", RuntimeWarning, stacklevel=2)

        self.providers_by_type.update({x.bound_type: x for x in kwargs.values() if x.bound_type})
