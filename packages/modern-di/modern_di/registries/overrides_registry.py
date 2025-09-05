import dataclasses
import typing


T_co = typing.TypeVar("T_co", covariant=True)


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class OverridesRegistry:
    overrides: dict[str, typing.Any] = dataclasses.field(init=False, default_factory=dict)

    def override(self, provider_id: str, override_object: object) -> None:
        self.overrides[provider_id] = override_object

    def reset_override(self, provider_id: str | None = None) -> None:
        if provider_id is None:
            self.overrides.clear()
        else:
            self.overrides.pop(provider_id, None)

    def fetch_override(self, provider_id: str) -> object | None:
        return self.overrides.get(provider_id)
