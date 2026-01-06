import typing

from modern_di.consts import UNSET
from modern_di.helpers.type_helpers import parse_signature
from modern_di.providers.abstract import AbstractProvider
from modern_di.scope import Scope


if typing.TYPE_CHECKING:
    from modern_di import Container


T_co = typing.TypeVar("T_co", covariant=True)
P = typing.ParamSpec("P")


def _resolve_kwargs(container: "Container", kwargs: dict[str, typing.Any]) -> dict[str, typing.Any]:
    result: dict[str, typing.Any] = {}
    for k, v in kwargs.items():
        if isinstance(v, AbstractProvider):
            result[k] = container.resolve_provider(v)
        elif isinstance(v, type):
            result[k] = container.resolve(v)
        else:
            result[k] = v
    return result


class Factory(AbstractProvider[T_co]):
    __slots__ = [*AbstractProvider.BASE_SLOTS, "creator", "kwargs", "singleton"]

    def __init__(
        self,
        *,
        scope: Scope = Scope.APP,
        creator: typing.Callable[..., T_co],
        bound_type: type | None = UNSET,  # type: ignore[assignment]
        kwargs: dict[str, typing.Any] | None = None,
        singleton: bool = False,
    ) -> None:
        signature = parse_signature(creator)
        super().__init__(scope=scope, bound_type=bound_type if bound_type != UNSET else signature.dependency_type)
        self.creator: typing.Final = creator
        self.singleton = singleton
        self.kwargs: dict[str, typing.Any] = signature.kwargs
        if kwargs:
            self.kwargs.update(kwargs)

    def resolve(self, container: "Container") -> T_co:
        if (override := container.overrides_registry.fetch_override(self.provider_id)) is not None:
            return typing.cast(T_co, override)

        kwargs = _resolve_kwargs(container, self.kwargs or {})

        if self.singleton:
            return self._resolve_singleton(container, kwargs=kwargs)

        return self.creator(**kwargs)

    def _resolve_singleton(self, container: "Container", kwargs: dict[str, typing.Any]) -> T_co:
        if (provider_state := container.state_registry.fetch_provider_state(self)) is not None:
            return provider_state

        if container.lock:
            container.lock.acquire()

        try:
            if (provider_state := container.state_registry.fetch_provider_state(self)) is not None:
                return provider_state

            instance = self.creator(**kwargs)
            container.state_registry.set_provider_state(self, instance)
            return instance
        finally:
            if container.lock:
                container.lock.release()
