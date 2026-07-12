"""Iterative depth-first walk of the static provider graph, emitted as an event stream.

``DependencyGraph.walk`` is the single traversal that other capabilities (validation,
the runtime cycle guard) consume. It is deliberately *explicit-stack* — no recursion —
because a later caller runs it inside a ``RecursionError`` handler near CPython's stack
limit, where headroom for a recursive walk is not guaranteed. The event order mirrors
``Container.validate``'s recursive ``_visit`` exactly, so a consumer can reproduce
validate()'s output byte-for-byte.

Import discipline: this module must not import ``Container`` (nor any concrete provider)
at runtime — ``container.py`` imports this module, so a runtime back-import would cycle.
"""

import typing
from typing import NamedTuple

from modern_di import exceptions
from modern_di.providers.abstract import AbstractProvider


if typing.TYPE_CHECKING:
    from modern_di import Container


class NodeEntered(NamedTuple):
    """A provider was reached for the first time, before its dependencies are read."""

    provider: "AbstractProvider[typing.Any]"


class Edge(NamedTuple):
    """A dependency edge from ``parent`` to ``dep`` via parameter ``name``."""

    parent: "AbstractProvider[typing.Any]"
    name: str
    dep: "AbstractProvider[typing.Any]"


class Cycle(NamedTuple):
    """A cycle closing on the active path; ``providers`` repeats the first node last."""

    providers: "list[AbstractProvider[typing.Any]]"


class DependenciesError(NamedTuple):
    """Reading ``provider``'s dependencies raised; it is then treated as having none."""

    provider: "AbstractProvider[typing.Any]"
    error: Exception


Event = NodeEntered | Edge | Cycle | DependenciesError


class DependencyGraph:
    """Stateless walker over the static provider graph rooted at a container's registry."""

    def walk(
        self,
        roots: "typing.Iterable[AbstractProvider[typing.Any]]",
        container: "Container",
    ) -> "typing.Iterator[Event]":
        """Pre-order DFS from each root, emitting the event stream.

        ``visiting``/``visited`` are shared across all roots: a node reached under an
        earlier root is neither re-entered nor re-descended when it reappears, and a root
        already visited is skipped entirely. All bookkeeping is keyed on ``provider_id``.
        """
        visiting: set[int] = set()
        visited: set[int] = set()
        for root in roots:
            yield from self._walk_from(root, container, visiting, visited)

    def _walk_from(
        self,
        start: "AbstractProvider[typing.Any]",
        container: "Container",
        visiting: set[int],
        visited: set[int],
    ) -> "typing.Iterator[Event]":
        """Explicit-stack DFS from ``start``; skip immediately if already seen."""
        if start.provider_id in visited or start.provider_id in visiting:
            return

        path: list[AbstractProvider[typing.Any]] = []
        stack: list[typing.Iterator[tuple[str, AbstractProvider[typing.Any]]]] = []
        yield from self._enter(start, container, visiting, path, stack)

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
            yield from self._enter(dep, container, visiting, path, stack)

    def _enter(
        self,
        provider: "AbstractProvider[typing.Any]",
        container: "Container",
        visiting: set[int],
        path: "list[AbstractProvider[typing.Any]]",
        stack: "list[typing.Iterator[tuple[str, AbstractProvider[typing.Any]]]]",
    ) -> "typing.Iterator[Event]":
        """Push ``provider`` onto the active path: emit NodeEntered, then read its deps.

        A ``ResolutionError`` from ``get_dependencies`` is emitted as ``DependenciesError``
        and the node is treated as having no dependencies (the walk continues).
        """
        visiting.add(provider.provider_id)
        path.append(provider)
        yield NodeEntered(provider)
        try:
            dependencies = provider.get_dependencies(container)
        except exceptions.ResolutionError as exc:
            yield DependenciesError(provider, exc)
            dependencies = {}
        stack.append(iter(dependencies.items()))
