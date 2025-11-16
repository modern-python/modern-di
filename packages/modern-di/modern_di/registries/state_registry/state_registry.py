import dataclasses
import typing

from modern_di.providers import AbstractProvider
from modern_di.registries.state_registry.state import ProviderState


T_co = typing.TypeVar("T_co", covariant=True)


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class StateRegistry:
    states: dict[str, ProviderState[typing.Any]] = dataclasses.field(init=False, default_factory=dict)

    def fetch_provider_state(self, provider: AbstractProvider[T_co]) -> ProviderState[T_co] | None:
        if not provider.HAS_STATE:
            return None

        if provider_state := self.states.get(provider.provider_id):
            return provider_state

        return self.states.setdefault(provider.provider_id, ProviderState())

    async def async_tear_down(self) -> None:
        for provider_state in reversed(self.states.values()):
            await provider_state.async_tear_down()

    def sync_tear_down(self) -> None:
        for provider_state in reversed(self.states.values()):
            provider_state.sync_tear_down()
