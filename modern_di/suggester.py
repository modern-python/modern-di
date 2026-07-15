import dataclasses
import difflib
import enum
import inspect
import typing


if typing.TYPE_CHECKING:
    from modern_di.providers.abstract import AbstractProvider


_MAX_SUGGESTIONS = 3


@dataclasses.dataclass(frozen=True, slots=True)
class Suggestion:
    """A candidate the caller probably meant, as data.

    Carries no formatting: rendering a suggestion to a bullet is ``exceptions``' job, so
    one module owns the glyphs. ``scope`` is None when the suggestion names something with
    no provider behind it (a creator's keyword argument); ``reason`` is None when there is
    nothing to say beyond the name.
    """

    name: str
    reason: str | None = None
    scope: enum.IntEnum | None = None


def suggest(requested_type: type, providers: "typing.Iterable[AbstractProvider[typing.Any]]") -> list[Suggestion]:
    """Candidates the caller may have meant for ``requested_type``, best first, as data.

    Class hierarchy hints (a registered subclass or base class of the requested type) come
    first, then fuzzy name matches, capped at ``_MAX_SUGGESTIONS``. Rendering belongs to
    ``exceptions``; this returns records, never bullets. ``providers`` is read by duck typing
    on ``bound_type``/``scope`` (annotated under ``TYPE_CHECKING`` to avoid an import cycle).
    """
    requested_is_class = inspect.isclass(requested_type)
    requested_name = getattr(requested_type, "__name__", str(requested_type))

    hierarchy_hints: list[Suggestion] = []
    name_to_scope: dict[str, enum.IntEnum] = {}

    for provider in list(providers):
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
            name_to_scope[name] = provider.scope

    remaining = _MAX_SUGGESTIONS - len(hierarchy_hints)
    typo_hints = [
        Suggestion(name=name, reason="similar name", scope=name_to_scope[name])
        for name in close_matches(requested_name, name_to_scope.keys(), n=remaining)
    ]
    return hierarchy_hints + typo_hints


def _hierarchy_hint(requested_type: type, provider: "AbstractProvider[typing.Any]") -> "Suggestion | None":
    """Return a subclass/base-class hint for a provider whose ``bound_type`` is a class, else None."""
    registered = provider.bound_type
    if registered is None or not inspect.isclass(registered):
        return None
    try:
        if issubclass(registered, requested_type):
            reason = "registered subclass"
        elif issubclass(requested_type, registered):
            reason = "registered base class"
        else:
            return None
    except TypeError:
        return None
    return Suggestion(name=registered.__name__, reason=reason, scope=provider.scope)


def close_matches(target: str, candidates: typing.Iterable[str], *, n: int, cutoff: float = 0.6) -> list[str]:
    """Fuzzy-match ``target`` against ``candidates``; best ``n`` at/above ``cutoff``.

    Thin wrapper over ``difflib.get_close_matches``. Shared by ``suggest`` (provider name
    typos) and ``UnknownFactoryKwargError`` (kwarg-key typos).
    """
    return difflib.get_close_matches(target, list(candidates), n=n, cutoff=cutoff)
