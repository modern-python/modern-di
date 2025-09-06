import dataclasses
import typing

from modern_di.providers import AbstractProvider
from modern_di.registries.state_registry.state import AsyncState, SyncState


T_co = typing.TypeVar("T_co", covariant=True)


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class AsyncStateRegistry:
    use_lock: bool
    states: dict[str, AsyncState[typing.Any]] = dataclasses.field(init=False, default_factory=dict)

    def fetch_provider_state(self, provider: AbstractProvider[T_co]) -> AsyncState[T_co] | None:
        if not provider.HAS_STATE:
            return None

        if provider_state := self.states.get(provider.provider_id):
            return provider_state

        # expected to be thread-safe, because setdefault is atomic
        return self.states.setdefault(provider.provider_id, AsyncState(use_lock=self.use_lock))

    async def clear_state(self) -> None:
        for provider_state in reversed(self.states.values()):
            await provider_state.tear_down()

        self.states.clear()


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SyncStateRegistry:
    use_lock: bool
    states: dict[str, SyncState[typing.Any]] = dataclasses.field(init=False, default_factory=dict)

    def fetch_provider_state(self, provider: AbstractProvider[T_co]) -> SyncState[T_co] | None:
        if not provider.HAS_STATE:
            return None

        if provider_state := self.states.get(provider.provider_id):
            return provider_state

        # expected to be thread-safe, because setdefault is atomic
        return self.states.setdefault(provider.provider_id, SyncState(use_lock=self.use_lock))

    def clear_state(self) -> None:
        for provider_state in reversed(self.states.values()):
            provider_state.tear_down()

        self.states.clear()
