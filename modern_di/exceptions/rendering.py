"""Chain and suggestion glyphs: the one place an error message's shape is drawn."""

import dataclasses
import enum

from modern_di import suggester


SUGGESTION_HEADER = "Did you mean:"


@dataclasses.dataclass(frozen=True, slots=True)
class ResolutionStep:
    """One entry in a chain-shaped error: a provider, as this module needs to draw it.

    Used both for a :class:`ResolutionError`'s ``dependency_path`` and for a
    :class:`CircularDependencyError`'s cycle, so both render through ``_render_chain``.

    Attributes:
        scope: the scope of the provider at this step of the chain.
        name: the provider's display name (bound type or creator name).
        location: the provider's declaration site as ``module:line``, when known.

    """

    scope: enum.IntEnum
    name: str
    location: str | None = None


def _render_chain(steps: "list[ResolutionStep]") -> list[str]:
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


def _render_suggestion_lines(suggestions: "list[suggester.Suggestion]") -> list[str]:
    """Draw each suggestion as a bullet. The single home of the suggestion glyphs."""
    lines = []
    for suggestion in suggestions:
        details = [x for x in (suggestion.reason, _scope_detail(suggestion.scope)) if x]
        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"  - {suggestion.name}{suffix}")
    return lines


def _scope_detail(scope: enum.IntEnum | None) -> str | None:
    return None if scope is None else f"scope={scope.name}"


def _render_suggestions(suggestions: "list[suggester.Suggestion]") -> str:
    """Render the full ``Did you mean:`` block, or an empty string when there is nothing to suggest."""
    if not suggestions:
        return ""
    return "\n".join([SUGGESTION_HEADER, *_render_suggestion_lines(suggestions)])
