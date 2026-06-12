import difflib
import inspect
import threading
import typing

from modern_di import errors, exceptions, types
from modern_di.providers.abstract import AbstractProvider


_MAX_SUGGESTIONS = 3
_SIMILARITY_CUTOFF = 0.6


def _hierarchy_hint(requested_type: type, provider: AbstractProvider[typing.Any]) -> str | None:
    registered = provider.bound_type
    if registered is None or not inspect.isclass(registered):
        return None
    try:
        if issubclass(registered, requested_type):
            return errors.SUGGESTION_SUBCLASS.format(type_name=registered.__name__, scope=provider.scope.name)
        if issubclass(requested_type, registered):
            return errors.SUGGESTION_BASECLASS.format(type_name=registered.__name__, scope=provider.scope.name)
    except TypeError:
        return None
    return None


class ProvidersRegistry:
    __slots__ = ("_lock", "_providers")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._providers: dict[type, AbstractProvider[typing.Any]] = {}

    def __len__(self) -> int:
        return len(self._providers)

    def __iter__(self) -> typing.Iterator[AbstractProvider[typing.Any]]:
        return iter(list(self._providers.values()))

    def find_provider(self, dependency_type: type[types.T]) -> AbstractProvider[types.T] | None:
        return self._providers.get(dependency_type)

    def register(self, provider_type: type, provider: AbstractProvider[typing.Any]) -> None:
        with self._lock:
            if provider_type in self._providers:
                raise exceptions.DuplicateProviderTypeError(provider_type=provider_type)
            self._providers[provider_type] = provider

    def add_providers(self, *args: AbstractProvider[typing.Any]) -> None:
        new_providers: dict[type, AbstractProvider[typing.Any]] = {}
        for provider in args:
            if not provider.bound_type:
                continue
            if provider.bound_type in new_providers:
                raise exceptions.DuplicateProviderTypeError(provider_type=provider.bound_type)
            new_providers[provider.bound_type] = provider

        with self._lock:
            for provider_type in new_providers:
                if provider_type in self._providers:
                    raise exceptions.DuplicateProviderTypeError(provider_type=provider_type)
            self._providers.update(new_providers)

    def build_suggestions(self, requested_type: type) -> list[str]:
        requested_is_class = inspect.isclass(requested_type)
        requested_name = getattr(requested_type, "__name__", str(requested_type))

        hierarchy_hints: list[str] = []
        name_to_provider: dict[str, AbstractProvider[typing.Any]] = {}

        for provider in list(self._providers.values()):
            registered = provider.bound_type
            if registered is None or registered is requested_type:
                continue

            hint = _hierarchy_hint(requested_type, provider) if requested_is_class else None
            if hint is not None:
                hierarchy_hints.append(hint)
                if len(hierarchy_hints) >= _MAX_SUGGESTIONS:
                    return hierarchy_hints
                continue

            name = getattr(registered, "__name__", None)
            if name:
                name_to_provider[name] = provider

        remaining = _MAX_SUGGESTIONS - len(hierarchy_hints)
        typo_hints = [
            errors.SUGGESTION_SIMILAR.format(type_name=name, scope=name_to_provider[name].scope.name)
            for name in difflib.get_close_matches(
                requested_name, name_to_provider.keys(), n=remaining, cutoff=_SIMILARITY_CUTOFF
            )
        ]
        return hierarchy_hints + typo_hints
