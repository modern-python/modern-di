import dataclasses
import typing

from modern_di.providers import Singleton


T_co = typing.TypeVar("T_co", covariant=True)


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class StateRegistry:
    states: dict[str, typing.Any] = dataclasses.field(init=False, default_factory=dict)

    def fetch_provider_state(self, provider: Singleton[T_co]) -> T_co | None:
        return self.states.get(provider.provider_id)

    def set_provider_state(self, provider: Singleton[T_co], instance: typing.Any) -> None:  # noqa: ANN401
        self.states[provider.provider_id] = instance
