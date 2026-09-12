"""Framework-agnostic primitives for building a modern-di integration.

`bind` and `classify_connection` decide what to pass `build_child_container`; they never open a
child themselves. The rest is the `Annotated`-marker injector for integrations with no native
per-handler seam.
"""

import dataclasses
import enum
import typing

from modern_di import types


_INJECTED_ATTR = "__modern_di_injected__"


if typing.TYPE_CHECKING:
    from modern_di.container import Container
    from modern_di.providers.abstract import AbstractProvider
    from modern_di.providers.context_provider import ContextProvider


@dataclasses.dataclass(frozen=True, slots=True)
class ConnectionMatch:
    """A child container's scope and context, derived from one connection."""

    scope: enum.IntEnum
    context: dict[type[typing.Any], typing.Any]


def bind(provider: "ContextProvider[typing.Any]", connection: object) -> ConnectionMatch:
    """Derive a child's scope and context, keyed as `build_child_container(context=...)` expects."""
    return ConnectionMatch(scope=provider.scope, context={provider.context_type: connection})


def classify_connection(
    connection: object, providers: "tuple[ContextProvider[typing.Any], ...]"
) -> ConnectionMatch | None:
    """Pick the first provider `connection` is an instance of and `bind` it; `None` when none matches."""
    for provider in providers:
        if isinstance(connection, provider.context_type):
            return bind(provider, connection)
    return None


@dataclasses.dataclass(frozen=True, slots=True)
class Marker(typing.Generic[types.T_co]):
    """What `resolve_dependency` should resolve for one `Annotated` parameter."""

    dependency: "AbstractProvider[types.T_co] | type[types.T_co]"

    def resolve(self, container: "Container") -> types.T_co:
        """Resolve this marker's dependency from `container`."""
        return container.resolve_dependency(self.dependency)


def from_di(dependency: "AbstractProvider[types.T] | type[types.T]") -> types.T:
    """Build the marker for one injected parameter.

    `Annotated[T, from_di(dep)]` type-checks as `T`.
    """
    return typing.cast(types.T, Marker(dependency))


def parse_markers(func: typing.Callable[..., typing.Any]) -> dict[str, Marker[typing.Any]]:
    """Scan `func`'s `Annotated` parameter hints for `Marker`s — at decoration time, not per call.

    The first `Marker` in a parameter's metadata wins; `return` is never scanned. An unresolvable
    forward reference propagates `get_type_hints`'s own error.
    """
    hints = typing.get_type_hints(func, include_extras=True)
    markers: dict[str, Marker[typing.Any]] = {}
    for name, hint in hints.items():
        if name == "return":
            continue
        if typing.get_origin(hint) is typing.Annotated:
            for meta in typing.get_args(hint)[1:]:
                if isinstance(meta, Marker):
                    markers[name] = meta
                    break
    return markers


def resolve_markers(container: "Container", markers: typing.Mapping[str, Marker[typing.Any]]) -> dict[str, typing.Any]:
    """Resolve every marker in `markers` from `container`, keyed by parameter name."""
    return {name: marker.resolve(container) for name, marker in markers.items()}


def is_injected(func: typing.Callable[..., typing.Any]) -> bool:
    """Whether `mark_injected` has already been applied to `func`."""
    return bool(getattr(func, _INJECTED_ATTR, False))


def mark_injected(wrapper: typing.Callable[..., typing.Any]) -> None:
    """Mark `wrapper` as already injected, so a later sweep skips re-wrapping it."""
    setattr(wrapper, _INJECTED_ATTR, True)
