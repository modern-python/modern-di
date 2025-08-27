import dataclasses
import typing

from modern_di.providers.abstract import AbstractProvider


@dataclasses.dataclass(slots=True, frozen=True)
class ProvidersRegistry:
    providers_by_name: dict[str, AbstractProvider[typing.Any]] = dataclasses.field(init=False, default_factory=dict)
    providers_by_type: dict[type, AbstractProvider[typing.Any]] = dataclasses.field(init=False, default_factory=dict)

    def find_provider(
        self, dependency_name: str | None = None, dependency_type: type | None = None
    ) -> AbstractProvider[typing.Any] | None:
        if dependency_name and (provider := self.providers_by_name.get(dependency_name)):
            return provider

        if dependency_type and (provider := self.providers_by_type.get(dependency_type)):
            return provider

        return None

    def add_providers(self, **kwargs: AbstractProvider[typing.Any]) -> None:
        self.providers_by_name.update(kwargs)
        self.providers_by_type.update({x.bounded_type: x for x in kwargs.values() if x.bounded_type})
