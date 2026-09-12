import dataclasses
import typing
from types import TracebackType

from modern_di import types


@dataclasses.dataclass(kw_only=True, slots=True)
class OverridesRegistry:
    """Test-time replacement values by provider id.

    Overrides are applied at compile time: every change calls ``on_change`` so the owning
    providers registry drops its compiled resolvers, and the next resolve recompiles with the
    override baked in. Nothing consults this registry on the resolve path.
    """

    on_change: typing.Callable[[], None]
    _overrides: dict[int, typing.Any] = dataclasses.field(init=False, default_factory=dict)

    def override(self, provider_id: int, override_object: object) -> None:
        self._overrides[provider_id] = override_object
        self.on_change()

    def reset_override(self, provider_id: int | None = None) -> None:
        if provider_id is None:
            if not self._overrides:
                return
            self._overrides.clear()
        elif self._overrides.pop(provider_id, types.UNSET) is types.UNSET:
            return
        self.on_change()

    def fetch_override(self, provider_id: int) -> object:
        return self._overrides.get(provider_id, types.UNSET)


class OverrideHandle(typing.Generic[types.T]):
    """Context-manager handle returned by ``Container.override``.

    The override is already active when the handle is created; ``__exit__`` restores the
    snapshot taken at creation — the prior override, or no override. Single-use contract.
    """

    __slots__ = ("_prior", "_provider_id", "_registry", "override_object")

    def __init__(
        self,
        *,
        registry: OverridesRegistry,
        provider_id: int,
        prior: object,
        override_object: types.T,
    ) -> None:
        self._registry = registry
        self._provider_id = provider_id
        self._prior = prior
        self.override_object = override_object

    def __enter__(self) -> types.T:
        return self.override_object

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if isinstance(self._prior, types.UnsetType):
            self._registry.reset_override(self._provider_id)
        else:
            self._registry.override(self._provider_id, self._prior)
