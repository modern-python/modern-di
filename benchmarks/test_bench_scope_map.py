# ruff: noqa: ANN001, ANN201
"""Benchmark: fix #2 — O(1) scope-map cache vs O(depth) parent-chain walk.

Three scenarios:
  find_same_scope   — requesting the current container's own scope (best case for both)
  find_parent_scope — requesting a grandparent scope (worst case for the walk)
  full_resolve      — end-to-end resolve() across a 4-level scope chain

Run:
    just bench
"""

import dataclasses

from modern_di import Container, Group, Scope, providers


# ---------------------------------------------------------------------------
# Baseline find_container — linear parent-chain walk (pre-fix #2)
# ---------------------------------------------------------------------------


def _baseline_find_container(self: Container, scope: Scope) -> Container:
    container = self
    if container.scope < scope:
        msg = f"Provider of scope {scope.name} cannot be resolved in container of scope {self.scope.name}."
        raise RuntimeError(msg)
    while container.scope > scope and container.parent_container:
        container = container.parent_container
    if container.scope != scope:
        msg = (
            f"No {scope.name}-scope container exists in this chain; "
            f"this chain starts at {self.scope.name}. "
            f"Build a {scope.name}-scope container as the root."
        )
        raise RuntimeError(msg)
    return container


# ---------------------------------------------------------------------------
# Subject graph — providers at each scope level
# ---------------------------------------------------------------------------


@dataclasses.dataclass(kw_only=True, slots=True)
class AppService:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class RequestService:
    app: AppService


class AppGroup(Group):
    svc = providers.Factory(scope=Scope.APP, creator=AppService)


class RequestGroup(Group):
    svc = providers.Factory(scope=Scope.REQUEST, creator=RequestService)


# ---------------------------------------------------------------------------
# Scenario 1 — find_container: same scope (depth-0 walk)
# ---------------------------------------------------------------------------


def test_find_same_scope_optimized(benchmark):
    c = Container(scope=Scope.APP, groups=[AppGroup])
    benchmark(c.find_container, Scope.APP)


def test_find_same_scope_baseline(benchmark):
    original = Container.find_container
    Container.find_container = _baseline_find_container  # ty: ignore[invalid-assignment]
    try:
        c = Container(scope=Scope.APP, groups=[AppGroup])
        benchmark(c.find_container, Scope.APP)
    finally:
        Container.find_container = original


# ---------------------------------------------------------------------------
# Scenario 2 — find_container: REQUEST scope from STEP container (depth-3 walk)
# ---------------------------------------------------------------------------


def test_find_parent_scope_optimized(benchmark):
    app = Container(scope=Scope.APP, groups=[AppGroup])
    sess = app.build_child_container(scope=Scope.SESSION)
    req = sess.build_child_container(scope=Scope.REQUEST)
    step = req.build_child_container(scope=Scope.STEP)
    benchmark(step.find_container, Scope.APP)


def test_find_parent_scope_baseline(benchmark):
    original = Container.find_container
    Container.find_container = _baseline_find_container  # ty: ignore[invalid-assignment]
    try:
        app = Container(scope=Scope.APP, groups=[AppGroup])
        sess = app.build_child_container(scope=Scope.SESSION)
        req = sess.build_child_container(scope=Scope.REQUEST)
        step = req.build_child_container(scope=Scope.STEP)
        benchmark(step.find_container, Scope.APP)
    finally:
        Container.find_container = original


# ---------------------------------------------------------------------------
# Scenario 3 — full resolve() with cross-scope dependency (APP provider from REQUEST container)
# ---------------------------------------------------------------------------


def test_full_resolve_cross_scope_optimized(benchmark):
    app = Container(scope=Scope.APP, groups=[AppGroup, RequestGroup])
    req = app.build_child_container(scope=Scope.SESSION).build_child_container(scope=Scope.REQUEST)
    benchmark(req.resolve_provider, RequestGroup.svc)


def test_full_resolve_cross_scope_baseline(benchmark):
    original = Container.find_container
    Container.find_container = _baseline_find_container  # ty: ignore[invalid-assignment]
    try:
        app = Container(scope=Scope.APP, groups=[AppGroup, RequestGroup])
        req = app.build_child_container(scope=Scope.SESSION).build_child_container(scope=Scope.REQUEST)
        benchmark(req.resolve_provider, RequestGroup.svc)
    finally:
        Container.find_container = original
