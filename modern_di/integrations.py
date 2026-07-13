"""Framework-agnostic primitives for building a modern-di integration.

Layer 1 (`bind`, `classify_connection`) derives a child container's scope and
context from one or more `ContextProvider`s. Neither wraps
`build_child_container` — the caller's own call to it stays the single
blessed way to open a child; these functions only decide what to pass it.
Layer 2 (`Marker`, `from_di`, `parse_markers`, `resolve_markers`) is the
`Annotated`-marker injector shared by every integration without a native
per-handler injection seam. `is_injected`/`mark_injected` guard against
double-wrapping a handler an auto-inject sweep visits more than once.
"""

import dataclasses
import enum
import typing

from modern_di import types


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
    """Derive a child's scope and context from one connection bound to one provider.

    `context` is keyed by `provider.context_type` — the same convention
    `build_child_container(context=...)` expects.
    """
    return ConnectionMatch(scope=provider.scope, context={provider.context_type: connection})


def classify_connection(
    connection: object, providers: "tuple[ContextProvider[typing.Any], ...]"
) -> ConnectionMatch | None:
    """Pick the first provider `connection` is an instance of and `bind` it.

    Returns `None` on no match rather than raising — the caller decides the
    fallback, matching every dispatch adapter's existing behavior of building
    an auto-scoped, context-less child when nothing matches.
    """
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
    """Marker factory for dependency injection.

    Default factory: `Annotated[T, from_di(dep)]` type-checks as `T`.
    Integrations with their own per-handler injection seam (native `Depends`)
    define their own factory instead; the rest re-export this one.
    """
    return typing.cast(types.T, Marker(dependency))
