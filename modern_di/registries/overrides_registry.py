import dataclasses
import typing

from modern_di import types


@dataclasses.dataclass(kw_only=True, slots=True)
class OverridesRegistry:
    overrides: dict[int, typing.Any] = dataclasses.field(init=False, default_factory=dict)

    def override(self, provider_id: int, override_object: object) -> None:
        self.overrides[provider_id] = override_object

    def reset_override(self, provider_id: int | None = None) -> None:
        if provider_id is None:
            self.overrides.clear()
        else:
            self.overrides.pop(provider_id, None)

    def fetch_override(self, provider_id: int) -> object:
        return self.overrides.get(provider_id, types.UNSET)
