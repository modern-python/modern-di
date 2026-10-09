"""Iterative depth-first walk of the static provider graph, emitted as an event stream.

Explicit-stack, never recursive: a caller runs it inside a ``RecursionError`` handler near
CPython's stack limit. Must not import ``Container`` or a concrete provider at runtime —
``container.py`` imports this module, so a back-import would cycle.
"""

import enum
import typing
from typing import NamedTuple

from modern_di import exceptions
from modern_di.providers.abstract import AbstractProvider


if typing.TYPE_CHECKING:
    from modern_di.registries.providers_registry import ProvidersRegistry


@typing.final
class NodeEntered(NamedTuple):
    """A provider was reached for the first time, before its dependencies are read."""

    provider: "AbstractProvider[typing.Any]"


@typing.final
class Edge(NamedTuple):
    """A dependency edge from ``parent`` to ``dep`` via parameter ``name``."""

    parent: "AbstractProvider[typing.Any]"
    name: str
    dep: "AbstractProvider[typing.Any]"


@typing.final
class Cycle(NamedTuple):
    """A cycle closing on the active path; ``providers`` repeats the first node last."""

    providers: "list[AbstractProvider[typing.Any]]"


@typing.final
class DependenciesError(NamedTuple):
    """Reading ``provider``'s dependencies raised; it is then treated as having none."""

    provider: "AbstractProvider[typing.Any]"
    error: Exception


Event = NodeEntered | Edge | Cycle | DependenciesError


def terminal_chain(
    provider: "AbstractProvider[typing.Any]", registry: "ProvidersRegistry"
) -> "list[AbstractProvider[typing.Any]]":
    """Follow ``_redirect_target`` hops from ``provider``, ``provider`` first.

    A redirect cycle collapses the chain to the single provider the repeat was detected at, so
    ``effective_scope`` reports that provider's own scope; ``walk()`` reports the cycle itself.
    """
    chain = [provider]
    seen: set[int] = set()
    while (nxt := provider._redirect_target(registry)) is not None:  # noqa: SLF001
        if provider.provider_id in seen:
            return [provider]
        seen.add(provider.provider_id)
        provider = nxt
        chain.append(provider)
    return chain


def effective_scope(provider: "AbstractProvider[typing.Any]", registry: "ProvidersRegistry") -> enum.IntEnum:
    """Return the scope a provider actually resolves at: its terminal's, once redirects are followed."""
    return terminal_chain(provider, registry)[-1].scope


def redirect_hops(
    provider: "AbstractProvider[typing.Any]", registry: "ProvidersRegistry"
) -> "list[exceptions.ResolutionStep]":
    """Return the chain steps for the redirects between ``provider`` and its terminal, terminal excluded.

    A redirect owns no lifetime of its own, so each hop is drawn at the scope the terminal resolves at.
    """
    *hops, terminal = terminal_chain(provider, registry)
    return [p._resolution_step(terminal.scope) for p in hops]  # noqa: SLF001


def build_cycle_error(
    providers: "list[AbstractProvider[typing.Any]]",
    registry: "ProvidersRegistry",
) -> "exceptions.CircularDependencyError":
    """Build a ``CircularDependencyError`` from a cycle's providers (first node repeated last).

    Rotated to start at the lowest ``provider_id``, so the message does not depend on which
    frame caught the ``RecursionError``.
    """
    ring = providers[:-1]
    lead = min(range(len(ring)), key=lambda i: ring[i].provider_id)
    rotated = [*ring[lead:], *ring[:lead]]
    canonical = [*rotated, rotated[0]]
    return exceptions.CircularDependencyError(
        steps=[p._resolution_step(effective_scope(p, registry)) for p in canonical]  # noqa: SLF001
    )


def walk(
    roots: "typing.Iterable[AbstractProvider[typing.Any]]",
    registry: "ProvidersRegistry",
) -> "typing.Iterator[Event]":
    """Pre-order DFS from each root; bookkeeping is shared across roots, keyed on ``provider_id``."""
    visiting: set[int] = set()
    visited: set[int] = set()
    for root in roots:
        if root.provider_id not in visited:
            yield from _walk_from(root, registry, visiting, visited)


def find_cycle_from(
    start: "AbstractProvider[typing.Any]",
    registry: "ProvidersRegistry",
) -> "list[AbstractProvider[typing.Any]] | None":
    """Return the first cycle reachable from ``start``, or None when that subgraph is acyclic."""
    for event in walk([start], registry):
        if isinstance(event, Cycle):
            return event.providers
    return None


def _walk_from(
    start: "AbstractProvider[typing.Any]",
    registry: "ProvidersRegistry",
    visiting: set[int],
    visited: set[int],
) -> "typing.Iterator[Event]":
    """Explicit-stack DFS from an unvisited ``start``."""
    path: list[AbstractProvider[typing.Any]] = []
    stack: list[typing.Iterator[tuple[str, AbstractProvider[typing.Any]]]] = []
    yield from _enter(start, registry, visiting, path, stack)

    while stack:
        try:
            name, dep = next(stack[-1])
        except StopIteration:
            finished = path.pop()
            stack.pop()
            visiting.discard(finished.provider_id)
            visited.add(finished.provider_id)
            continue

        yield Edge(path[-1], name, dep)
        if dep.provider_id in visiting:
            cycle_start = next(i for i, p in enumerate(path) if p.provider_id == dep.provider_id)
            yield Cycle([*path[cycle_start:], path[cycle_start]])
            continue
        if dep.provider_id in visited:
            continue
        yield from _enter(dep, registry, visiting, path, stack)


def _enter(
    provider: "AbstractProvider[typing.Any]",
    registry: "ProvidersRegistry",
    visiting: set[int],
    path: "list[AbstractProvider[typing.Any]]",
    stack: "list[typing.Iterator[tuple[str, AbstractProvider[typing.Any]]]]",
) -> "typing.Iterator[Event]":
    """Push ``provider`` onto the active path; a ``ResolutionError`` from it becomes ``DependenciesError``."""
    visiting.add(provider.provider_id)
    path.append(provider)
    yield NodeEntered(provider)
    try:
        dependencies = provider._get_dependencies(registry)  # noqa: SLF001
    except exceptions.ResolutionError as exc:
        yield DependenciesError(provider, exc)
        dependencies = {}
    stack.append(iter(dependencies.items()))


def collect_errors(registry: "ProvidersRegistry") -> list[Exception]:
    """Walk the graph rooted at ``registry``'s providers once; return every wiring error in walk order."""
    errors: list[Exception] = []
    for event in walk(roots=registry, registry=registry):
        if type(event) is Edge:
            parent, name, dep = event
            dependency_chain = terminal_chain(dep, registry)
            if dependency_chain[-1]._ignores_scope:  # noqa: SLF001
                continue
            dependency_scope = dependency_chain[-1].scope
            parent_scope = effective_scope(parent, registry)
            if dependency_scope > parent_scope:
                errors.append(
                    exceptions.InvalidScopeDependencyError(
                        provider=parent,
                        parameter_name=name,
                        dependency_chain=dependency_chain,
                    )
                )
            elif dependency_scope == parent_scope and dependency_scope is not parent_scope:
                errors.append(
                    exceptions.ScopeEnumMismatchError(
                        provider=parent,
                        parameter_name=name,
                        dependency_chain=dependency_chain,
                    )
                )
        elif type(event) is NodeEntered:
            errors.extend(event.provider._iter_validation_issues(registry))  # noqa: SLF001
        elif type(event) is DependenciesError:
            errors.append(event.error)
        else:
            errors.append(build_cycle_error(event.providers, registry))
    return errors
