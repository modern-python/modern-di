"""Chain and suggestion glyphs: the one place an error message's shape is drawn."""

import dataclasses
import enum
import typing

from modern_di import suggester


if typing.TYPE_CHECKING:
    from modern_di.providers.abstract import AbstractProvider


SUGGESTION_HEADER = "Did you mean:"


@dataclasses.dataclass(frozen=True, slots=True)
class ResolutionStep:
    """One entry in a chain-shaped error: a provider, as this module needs to draw it.

    Used both for a :class:`ResolutionError`'s ``dependency_path`` and for a
    :class:`CircularDependencyError`'s cycle, so both render through ``render_chain``.

    Attributes:
        scope: the scope of the provider at this step of the chain.
        name: the provider's display name (bound type or creator name).
        location: the provider's declaration site as ``module:line``, when known.

    """

    scope: enum.IntEnum
    name: str
    location: str | None = None


def provider_step(provider: "AbstractProvider[typing.Any]", scope: enum.IntEnum | None = None) -> ResolutionStep:
    """Return ``provider`` as a chain step at ``scope``, its own scope by default."""
    return ResolutionStep(
        scope=provider.scope if scope is None else scope, name=provider.display_name, location=provider.definition_site
    )


def render_provider_lines(providers: "list[AbstractProvider[typing.Any]]") -> list[str]:
    """Draw providers as a bulleted list: each by its kind and declaration site, else by its repr."""
    lines = []
    for provider in providers:
        site = provider.definition_site
        lines.append(f"  - {type(provider).__name__} ({site})" if site else f"  - {provider!r}")
    return lines


def render_chain(steps: "list[ResolutionStep]") -> list[str]:
    """Draw a provider chain as an indented arrow tree, one line per step.

    The single home of the chain glyphs — used by every chain-shaped error, so a
    resolution path and a dependency cycle cannot drift apart in how they read.
    """
    scope_width = max(len(step.scope.name) for step in steps)
    lines = []
    for i, step in enumerate(steps):
        prefix = "" if i == 0 else "    " * (i - 1) + "└─> "
        label = f"{step.name} ({step.location})" if step.location else step.name
        lines.append(f"  {step.scope.name:<{scope_width}}  {prefix}{label}")
    return lines


def type_name(type_: object) -> str:
    """Return a type's bare name, or its repr when it is parameterized or has no name."""
    name = getattr(type_, "__name__", None)
    if name is None or typing.get_origin(type_) is not None:
        return repr(type_)
    return str(name)


def render_suggestion_lines(suggestions: "list[suggester.Suggestion]") -> list[str]:
    """Draw each suggestion as a bullet. The single home of the suggestion glyphs."""
    lines = []
    for suggestion in suggestions:
        details = [x for x in (suggestion.reason, _scope_detail(suggestion.scope)) if x]
        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"  - {suggestion.name}{suffix}")
    return lines


def _scope_detail(scope: enum.IntEnum | None) -> str | None:
    return None if scope is None else f"scope={scope.name}"


def render_suggestions(suggestions: "list[suggester.Suggestion]") -> str:
    """Render the full ``Did you mean:`` block, or an empty string when there is nothing to suggest."""
    if not suggestions:
        return ""
    return "\n".join([SUGGESTION_HEADER, *render_suggestion_lines(suggestions)])
