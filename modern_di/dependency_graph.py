"""Iterative depth-first walk of the static provider graph, emitted as an event stream.

Explicit-stack, never recursive: a caller runs it inside a ``RecursionError`` handler near
CPython's stack limit. Dispatches on the closed provider set by type, like the resolver compiler.
Must not import ``Container`` at runtime: ``container.py`` imports this module.
"""

import enum
import typing
from typing import NamedTuple

from modern_di import exceptions
from modern_di.exceptions.rendering import provider_step
from modern_di.providers.abstract import AbstractProvider
from modern_di.providers.alias import Alias
from modern_di.providers.container_provider import container_provider
from modern_di.providers.factory import Factory
from modern_di.wiring import argument_resolution_error


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


def redirect_target(
    provider: "AbstractProvider[typing.Any]", registry: "ProvidersRegistry"
) -> "AbstractProvider[typing.Any] | None":
    """Return the provider ``provider`` transparently forwards to, or None if resolution terminates at it."""
    if type(provider) is Alias:
        return registry.find_provider(provider._source_type)  # noqa: SLF001
    return None


def dependencies_of(
    provider: "AbstractProvider[typing.Any]", registry: "ProvidersRegistry"
) -> dict[str, "AbstractProvider[typing.Any]"]:
    """Return parameter name to dependency provider: a pure registry lookup, no scope or cache touched."""
    if type(provider) is Factory:
        return registry.plan_for(provider).provider_kwargs
    if type(provider) is Alias:
        source = redirect_target(provider, registry)
        if source is None:
            raise exceptions.AliasSourceNotRegisteredError(source_type=provider._source_type)  # noqa: SLF001
        return {"source": source}
    return {}


def terminal_chain(
    provider: "AbstractProvider[typing.Any]", registry: "ProvidersRegistry"
) -> "list[AbstractProvider[typing.Any]]":
    """Follow ``redirect_target`` hops from ``provider``, ``provider`` first.

    A redirect cycle collapses the chain to the single provider the repeat was detected at, so
    ``effective_scope`` reports that provider's own scope; ``walk()`` reports the cycle itself.
    """
    chain = [provider]
    seen: set[int] = set()
    while (nxt := redirect_target(provider, registry)) is not None:
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
    return [provider_step(p, terminal.scope) for p in hops]


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
    return exceptions.CircularDependencyError(steps=[provider_step(p, effective_scope(p, registry)) for p in canonical])


def walk(
    roots: "typing.Iterable[AbstractProvider[typing.Any]]",
    registry: "ProvidersRegistry",
) -> "typing.Iterator[Event]":
    """Pre-order explicit-stack DFS from each root; bookkeeping is shared across roots, keyed on ``provider_id``.

    A ``ResolutionError`` from a provider's dependencies becomes a ``DependenciesError`` event.
    """
    visiting: set[int] = set()
    visited: set[int] = set()
    path: list[AbstractProvider[typing.Any]] = []
    stack: list[typing.Iterator[tuple[str, AbstractProvider[typing.Any]]]] = []
    for root in roots:
        if root.provider_id in visited:
            continue
        entering: AbstractProvider[typing.Any] | None = root
        while True:
            if entering is not None:
                visiting.add(entering.provider_id)
                path.append(entering)
                yield NodeEntered(entering)
                try:
                    dependencies = dependencies_of(entering, registry)
                except exceptions.ResolutionError as exc:
                    yield DependenciesError(entering, exc)
                    dependencies = {}
                stack.append(iter(dependencies.items()))
                entering = None
            if not stack:
                break
            step = next(stack[-1], None)
            if step is None:
                finished_id = path.pop().provider_id
                stack.pop()
                visiting.discard(finished_id)
                visited.add(finished_id)
                continue
            name, dep = step
            yield Edge(path[-1], name, dep)
            dep_id = dep.provider_id
            if dep_id in visiting:
                cycle_start = next(i for i, p in enumerate(path) if p.provider_id == dep_id)
                yield Cycle([*path[cycle_start:], path[cycle_start]])
            elif dep_id not in visited:
                entering = dep


def find_cycle_from(
    start: "AbstractProvider[typing.Any]",
    registry: "ProvidersRegistry",
) -> "list[AbstractProvider[typing.Any]] | None":
    """Return the first cycle reachable from ``start``, or None when that subgraph is acyclic."""
    for event in walk([start], registry):
        if isinstance(event, Cycle):
            return event.providers
    return None


def collect_errors(registry: "ProvidersRegistry") -> list[Exception]:
    """Walk the graph rooted at ``registry``'s providers once; return every wiring error in walk order."""
    errors: list[Exception] = []
    for event in walk(roots=registry, registry=registry):
        if type(event) is Edge:
            parent, name, dep = event
            dependency_chain = terminal_chain(dep, registry)
            if dependency_chain[-1] is container_provider:
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
            provider = event.provider
            if type(provider) is Factory:
                for name, item in registry.plan_for(provider).unwireable:
                    errors.append(argument_resolution_error(provider, name, item, registry))
        elif type(event) is DependenciesError:
            errors.append(event.error)
        else:
            errors.append(build_cycle_error(event.providers, registry))
    return errors
