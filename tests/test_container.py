import copy
import dataclasses
import enum
import gc
import inspect
import threading
import traceback
import typing
import weakref

import pytest

from modern_di import Container, Group, Scope, dependency_graph, exceptions, providers, suggester
from modern_di.dependency_graph import collect_errors, dependencies_of
from modern_di.exceptions import (
    ArgumentResolutionError,
    ChildContainerRegistrationError,
    CircularDependencyError,
    ContainerClosedError,
    DuplicateProviderTypeError,
    InvalidChildScopeError,
    InvalidScopeDependencyError,
    InvalidScopeTypeError,
    MaxScopeReachedError,
    ProviderNotRegisteredError,
    ScopeSkippedError,
    ValidationFailedError,
)
from modern_di.providers.abstract import AbstractProvider
from modern_di.registries.providers_registry import ProvidersRegistry
from tests.helpers import cache_item


def test_container_prevent_copy() -> None:
    container = Container()
    container_deepcopy = copy.deepcopy(container)
    container_copy = copy.copy(container)
    assert container_deepcopy is container_copy is container


def test_container_scope_skipped() -> None:
    app_factory = providers.Factory(creator=lambda: "test")
    container = Container(scope=Scope.REQUEST)
    with pytest.raises(ScopeSkippedError, match=r"No APP-scope container exists in this chain") as exc:
        container.resolve_provider(app_factory)
    assert exc.value.provider_scope == Scope.APP


def test_scope_skipped_error_names_the_root_of_the_chain() -> None:
    app_factory = providers.Factory(creator=lambda: "test")
    request_container = Container(scope=Scope.SESSION).build_child_container(scope=Scope.REQUEST)
    with pytest.raises(ScopeSkippedError) as exc:
        request_container.resolve_provider(app_factory)
    assert (
        "No APP-scope container exists in this chain, which starts at SESSION. Build the root container at scope APP."
    ) in str(exc.value)
    assert exc.value.root_scope is Scope.SESSION


def test_scope_skipped_error_for_a_scope_skipped_mid_chain() -> None:
    request_factory = providers.Factory(scope=Scope.REQUEST, creator=lambda: "test")
    action_container = Container().build_child_container(scope=Scope.ACTION)
    with pytest.raises(ScopeSkippedError) as exc:
        action_container.resolve_provider(request_factory)
    assert (
        "No REQUEST-scope container exists in this chain, which runs from APP to ACTION. "
        "Add a container at scope REQUEST to the chain."
    ) in str(exc.value)
    assert exc.value.root_scope is Scope.APP


def test_container_build_child() -> None:
    app_container = Container()
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    assert request_container.scope == Scope.REQUEST
    assert app_container.scope == Scope.APP


def test_container_scope_limit_reached() -> None:
    step_container = Container(scope=Scope.STEP)
    with pytest.raises(MaxScopeReachedError, match=r"Max scope of STEP is reached.") as exc:
        step_container.build_child_container()
    assert exc.value.parent_scope == Scope.STEP


def test_container_build_child_wrong_scope() -> None:
    app_container = Container()
    with pytest.raises(InvalidChildScopeError, match="Scope of child container cannot be") as exc:
        app_container.build_child_container(scope=Scope.APP)
    assert exc.value.parent_scope == Scope.APP
    assert exc.value.child_scope == Scope.APP


def test_container_resolve_missing_provider() -> None:
    app_container = Container()
    with pytest.raises(
        ProviderNotRegisteredError,
        match=r"No provider is registered for str\.",
    ) as exc:
        app_container.resolve(str)
    assert exc.value.dependency_type is str


def test_container_sync_context_manager() -> None:
    cleaned_up: list[str] = []

    class G(Group):
        resource = providers.Factory(
            creator=lambda: "r",
            bound_type=str,
            cache=providers.CacheSettings(finalizer=cleaned_up.append),
        )

    with Container(groups=[G]) as container:
        assert container.scope == Scope.APP
        assert container.resolve(str) == "r"
        with container.build_child_container(scope=Scope.REQUEST) as request_container:
            assert request_container.scope == Scope.REQUEST
    assert cleaned_up == ["r"]


async def test_container_async_context_manager() -> None:
    cleaned_up: list[str] = []

    async def collect(value: str) -> None:
        cleaned_up.append(value)

    class G(Group):
        resource = providers.Factory(
            creator=lambda: "r",
            bound_type=str,
            cache=providers.CacheSettings(finalizer=collect),
        )

    async with Container(groups=[G]) as container:
        assert container.scope == Scope.APP
        assert container.resolve(str) == "r"
        async with container.build_child_container(scope=Scope.REQUEST) as request_container:
            assert request_container.scope == Scope.REQUEST
    assert cleaned_up == ["r"]


def test_container_repr() -> None:
    container = Container()
    assert repr(container) == "Container(scope=APP, parent=None, providers=1, cached=0)"

    request_container = container.build_child_container(scope=Scope.REQUEST)
    assert repr(request_container) == "Container(scope=REQUEST, parent=APP, providers=1, cached=0)"


@dataclasses.dataclass(kw_only=True, slots=True)
class CycleA:
    dep: "CycleB"


@dataclasses.dataclass(kw_only=True, slots=True)
class CycleB:
    dep: CycleA


class CycleGroup(Group):
    a = providers.Factory(creator=CycleA)
    b = providers.Factory(creator=CycleB)


def test_cycle_path_carries_definition_sites() -> None:
    container = Container(groups=[CycleGroup])
    with pytest.raises(ValidationFailedError) as exc_info:
        container.validate()
    [issue] = exc_info.value.exceptions
    rendered = str(issue)
    lineno = inspect.getsourcelines(CycleA)[1]
    assert f"({CycleA.__module__}:{lineno})" in rendered


def test_validate_detects_cycle() -> None:
    container = Container(groups=[CycleGroup])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.exceptions
    assert isinstance(issue, CircularDependencyError)
    cycle = issue.cycle_path
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"CycleA", "CycleB"}


def test_validate_passes_for_valid_graph() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Dep:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        dep: Dep

    class ValidGroup(Group):
        dep = providers.Factory(creator=Dep)
        svc = providers.Factory(creator=Service)

    container = Container(groups=[ValidGroup])
    container.validate()  # should not raise


def test_validate_memoizes_diamond(monkeypatch: pytest.MonkeyPatch) -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Bottom:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Left:
        bottom: Bottom

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Right:
        bottom: Bottom

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Top:
        left: Left
        right: Right

    bottom_provider = providers.Factory(creator=Bottom)
    reads: list[AbstractProvider[typing.Any]] = []

    def counting_dependencies_of(
        provider: AbstractProvider[typing.Any], registry: ProvidersRegistry
    ) -> dict[str, AbstractProvider[typing.Any]]:
        reads.append(provider)
        return dependencies_of(provider, registry)

    monkeypatch.setattr(dependency_graph, "dependencies_of", counting_dependencies_of)

    class DiamondGroup(Group):
        bottom = bottom_provider
        left = providers.Factory(creator=Left)
        right = providers.Factory(creator=Right)
        top = providers.Factory(creator=Top)

    container = Container(groups=[DiamondGroup])
    container.validate()
    assert reads.count(bottom_provider) == 1


def test_validate_walks_deeper_scoped_providers() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        pass

    class G(Group):
        svc = providers.Factory(scope=Scope.REQUEST, creator=Service)

    Container(groups=[G]).validate()  # must not raise


def test_validate_raises_on_inverted_scope_dependency() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Inner:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Outer:
        inner: Inner

    class G(Group):
        inner = providers.Factory(scope=Scope.REQUEST, creator=Inner)
        outer = providers.Factory(scope=Scope.APP, creator=Outer)

    container = Container(groups=[G])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.exceptions
    assert isinstance(issue, InvalidScopeDependencyError)
    assert issue.parameter_name == "inner"
    assert issue.provider.scope == Scope.APP
    assert issue.dependency_provider.scope == Scope.REQUEST


def test_validate_raises_on_inverted_scope_dependency_supplied_via_kwargs() -> None:
    """A `kwargs=`-supplied provider is a real edge: its scope is checked like any other."""

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Inner:
        pass

    class Outer:
        # `inner: object` never type-matches; the edge exists only via the kwargs overlay.
        def __init__(self, inner: object = None) -> None: ...

    inner = providers.Factory(scope=Scope.REQUEST, creator=Inner)
    outer = providers.Factory(scope=Scope.APP, creator=Outer, kwargs={"inner": inner})

    container = Container()
    container.add_providers(inner, outer)

    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.exceptions
    assert isinstance(issue, InvalidScopeDependencyError)
    assert issue.parameter_name == "inner"
    assert issue.provider.scope == Scope.APP
    assert issue.dependency_provider.scope == Scope.REQUEST


def test_validate_raises_on_missing_required_dependency() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        missing: Missing

    class G(Group):
        svc = providers.Factory(creator=Service)

    container = Container(groups=[G])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.exceptions
    assert isinstance(issue, ArgumentResolutionError)
    assert issue.parameter_name == "missing"


def test_validate_accumulates_multiple_errors() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Inner:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Outer:
        inner: Inner

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Bad:
        missing: Missing

    class G(Group):
        inner = providers.Factory(scope=Scope.REQUEST, creator=Inner)
        outer = providers.Factory(scope=Scope.APP, creator=Outer)
        bad = providers.Factory(creator=Bad)
        cycle_a = providers.Factory(creator=CycleA)
        cycle_b = providers.Factory(creator=CycleB)

    container = Container(groups=[G])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    error_types = {type(e) for e in exc.value.exceptions}
    assert InvalidScopeDependencyError in error_types
    assert ArgumentResolutionError in error_types
    assert CircularDependencyError in error_types


def test_collect_errors_returns_flat_list_in_walk_order() -> None:
    class _Missing: ...

    @dataclasses.dataclass(kw_only=True, slots=True)
    class _NeedsMissing:
        missing: _Missing

    class G(Group):
        a = providers.Factory(creator=CycleA)
        b = providers.Factory(creator=CycleB)
        svc = providers.Factory(creator=_NeedsMissing)

    container = Container(scope=Scope.APP, groups=[G])
    errors = collect_errors(container._providers_registry)

    # Root order is registration order (a, b, svc): the cycle closes while walking from root
    # `a`, so it is appended before `svc`'s missing dependency is reached.
    error_types = [type(error).__name__ for error in errors]
    assert error_types == ["CircularDependencyError", "ArgumentResolutionError"]


def test_validate_detects_cycle_across_scopes() -> None:
    class CrossScopeCycleGroup(Group):
        a = providers.Factory(scope=Scope.REQUEST, creator=CycleA)
        b = providers.Factory(scope=Scope.REQUEST, creator=CycleB)

    container = Container(groups=[CrossScopeCycleGroup])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.exceptions
    assert isinstance(issue, CircularDependencyError)


def test_validate_handles_factory_with_static_kwargs() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        name: str

    class G(Group):
        svc = providers.Factory(creator=Service, kwargs={"name": "static"})

    Container(groups=[G]).validate()  # must not raise


def test_validation_failed_error_details_come_from_the_traceback_tree() -> None:
    container = Container(groups=[CycleGroup])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    assert str(exc.value) == (
        "Container.validate() found 1 issue(s): CircularDependencyError (1)\n"
        "See: https://modern-di.modern-python.org/troubleshooting/validation-failed-error/"
    )
    formatted = "".join(traceback.format_exception(exc.value))
    assert formatted.count("Circular dependency detected") == 1


def test_constructor_rejects_use_lock() -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument 'use_lock'"):
        Container(use_lock=False)  # ty: ignore[unknown-argument]


def test_container_provider_resolves_on_subclasses() -> None:
    class MyContainer(Container):
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        di_container: Container

    class G(Group):
        svc = providers.Factory(creator=Service)

    container = MyContainer(groups=[G])
    instance = container.resolve(Service)
    assert instance.di_container is container


def test_container_rejects_non_intenum_scope_at_init() -> None:
    with pytest.raises(InvalidScopeTypeError) as exc:
        Container(scope=99)  # ty: ignore[invalid-argument-type]
    assert "99" in str(exc.value)


def test_constructor_takes_only_scope_positionally() -> None:
    class G(Group):
        name = providers.Factory(creator=lambda: "r", bound_type=str)

    with pytest.raises(TypeError, match="positional arguments"):
        Container(Scope.APP, None)  # ty: ignore[too-many-positional-arguments]

    assert Container(Scope.APP).scope is Scope.APP
    with Container(scope=Scope.APP, groups=[G]) as container:
        assert container.resolve(str) == "r"


def test_constructor_builds_roots_only() -> None:
    app = Container(scope=Scope.APP)
    with pytest.raises(TypeError, match="parent_container"):
        Container(scope=Scope.REQUEST, parent_container=app)  # ty: ignore[unknown-argument]
    assert Container(scope=Scope.REQUEST).parent_container is None


def test_build_child_container_rejects_non_intenum_scope() -> None:
    with pytest.raises(InvalidScopeTypeError, match="99"):
        Container().build_child_container(scope=99)  # ty: ignore[invalid-argument-type]


def test_build_child_container_rejects_non_increasing_scope() -> None:
    app = Container(scope=Scope.APP)
    with pytest.raises(InvalidChildScopeError):
        app.build_child_container(scope=Scope.APP)
    request = app.build_child_container(scope=Scope.REQUEST)
    with pytest.raises(InvalidChildScopeError):
        request.build_child_container(scope=Scope.SESSION)


def test_build_child_container_keeps_the_subclass() -> None:
    class MyContainer(Container):
        pass

    child = MyContainer().build_child_container()
    assert type(child) is MyContainer
    assert type(child.build_child_container()) is MyContainer


def test_build_child_container_does_not_call_a_subclass_init() -> None:
    calls: list[enum.IntEnum] = []

    class TrackingContainer(Container):
        def __init__(self, scope: enum.IntEnum = Scope.APP, *, groups: list[type[Group]] | None = None) -> None:
            calls.append(scope)
            super().__init__(scope, groups=groups)

    class G(Group):
        name = providers.Factory(creator=lambda: "r", bound_type=str)

    root = TrackingContainer(groups=[G])
    child = root.build_child_container(scope=Scope.REQUEST, context={int: 1})
    assert calls == [Scope.APP]
    assert type(child) is TrackingContainer
    assert child.parent_container is root
    assert child.scope is Scope.REQUEST
    assert child.resolve(str) == "r"
    assert child.resolve(Container) is child


@pytest.mark.parametrize("attribute", ["scope", "parent_container"])
def test_container_state_is_read_only(attribute: str) -> None:
    root = Container()
    child = root.build_child_container()
    with pytest.raises(AttributeError):
        setattr(child, attribute, getattr(root, attribute))


class _PersistentBroker: ...


class _AppBrokerGroup(Group):
    broker = providers.Factory(
        scope=Scope.APP, creator=_PersistentBroker, cache=providers.CacheSettings(clear_cache=False)
    )


def test_resolve_on_closed_container_raises() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.raises(ContainerClosedError) as exc:
        container.resolve(Container)
    assert exc.value.container_scope is Scope.APP
    assert container.closed is True


def test_resolve_provider_on_closed_container_raises() -> None:
    container = Container(scope=Scope.APP, groups=[_AppBrokerGroup])
    container.close_sync()
    with pytest.raises(ContainerClosedError) as exc:
        container.resolve_provider(_AppBrokerGroup.broker)
    assert exc.value.container_scope is Scope.APP
    assert container.closed is True


def test_resolve_unregistered_type_on_closed_container_raises_closed() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.raises(ContainerClosedError) as exc:
        container.resolve(_PersistentBroker)
    assert exc.value.container_scope is Scope.APP


def test_resolve_provider_unregistered_on_closed_container_raises_closed() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.raises(ContainerClosedError):
        container.resolve_provider(_AppBrokerGroup.broker)


def test_reenter_reopens_closed_container() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with container:  # __enter__ -> open() clears closed
        assert container.resolve(Container) is container


async def test_closed_container_async_path_raises() -> None:
    container = Container(scope=Scope.APP)
    await container.close_async()
    with pytest.raises(ContainerClosedError):
        container.resolve(Container)


async def test_closed_container_async_path_raises_by_reference() -> None:
    container = Container(scope=Scope.APP, groups=[_AppBrokerGroup])
    await container.close_async()
    with pytest.raises(ContainerClosedError):
        container.resolve_provider(_AppBrokerGroup.broker)


def test_resolving_through_closed_parent_via_open_child_raises() -> None:
    app = Container(scope=Scope.APP, groups=[_AppBrokerGroup])
    child = app.build_child_container(scope=Scope.REQUEST)
    app.close_sync()
    with pytest.raises(ContainerClosedError) as exc:
        child.resolve(_PersistentBroker)
    assert exc.value.container_scope is Scope.APP
    assert app.closed is True
    assert "cached=0" in repr(app)


async def test_async_context_manager_reopens() -> None:
    container = Container(scope=Scope.APP)
    async with container:
        pass
    with pytest.raises(ContainerClosedError):
        container.resolve(Container)
    async with container:
        assert container.resolve(Container) is container


def test_open_reopens_closed_container() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.raises(ContainerClosedError):
        container.resolve(Container)
    container.open()
    assert container.resolve(Container) is container
    assert container.build_child_container(scope=Scope.REQUEST).scope is Scope.REQUEST


def test_closed_container_raises_before_running_the_creator() -> None:
    calls: list[str] = []

    class G(Group):
        f = providers.Factory(creator=lambda: calls.append("built") or "r", bound_type=str, cache=True)

    container = Container(scope=Scope.APP, groups=[G])
    container.close_sync()
    with pytest.raises(ContainerClosedError):
        container.resolve(str)
    assert calls == []
    assert "cached=0" in repr(container)


def test_reopen_rebuilds_a_value_that_close_cleared() -> None:
    class Svc: ...

    finalized: list[Svc] = []

    class G(Group):
        svc = providers.Factory(creator=Svc, cache=providers.CacheSettings(finalizer=finalized.append))

    container = Container(groups=[G])
    first = container.resolve(Svc)
    container.close_sync()
    assert finalized == [first]
    with pytest.raises(ContainerClosedError):
        container.resolve(Svc)
    with container:
        second = container.resolve(Svc)
    assert second is not first
    assert finalized == [first, second]


def test_child_built_off_closed_parent_raises_only_when_the_parent_resolves() -> None:
    """INVARIANT: building a child container does not require the parent to be open.

    `build_child_container` reads the parent's scope map and its two shared registries; it resolves
    nothing and touches no cache, so there is deliberately no closed-check on the parent. Adding one
    would break every integration that builds a request child after a shutdown/restart cycle.
    """
    app = Container(scope=Scope.APP, groups=[_AppBrokerGroup])
    app.close_sync()
    child = app.build_child_container(scope=Scope.REQUEST)
    assert child.resolve(Container) is child
    with pytest.raises(ContainerClosedError):
        child.resolve(_PersistentBroker)  # navigates to the closed APP owner


def test_container_closed_error_message_and_attr() -> None:
    err = ContainerClosedError(container_scope=Scope.APP)
    assert err.container_scope is Scope.APP
    assert "scope APP" in str(err)
    assert "is closed" in str(err)
    assert "open()" in str(err)
    assert str(err).endswith("/container-closed-error/")


def test_open_on_open_container_is_noop() -> None:
    with Container(scope=Scope.APP) as container:
        container.open()
        assert container.closed is False
        assert container.resolve(Container) is container


# --- a container is open from construction ------------------------------------------------------


def test_fresh_container_is_open() -> None:
    container = Container(scope=Scope.APP)
    assert container.closed is False


def test_fresh_container_resolves_without_open() -> None:
    container = Container(scope=Scope.APP)
    assert container.resolve(Container) is container
    assert container.closed is False


def test_fresh_container_builds_child_and_child_resolves_without_open() -> None:
    app = Container(scope=Scope.APP)
    child = app.build_child_container(scope=Scope.REQUEST)
    assert child.resolve(Container) is child
    assert app.closed is False  # building a child does not close the parent


def test_warm_cached_resolve_does_not_wait_for_the_item_lock() -> None:
    """A cached value resolves while another thread holds its cache item's lock.

    The lock is taken only on a cache miss. If a warm resolve took it too, the worker would block
    until the join timeout and the test would fail instead of hanging.
    """
    root = Container(scope=Scope.APP, groups=[_AppBrokerGroup])
    warm = root.resolve(_PersistentBroker)
    child = root.build_child_container(scope=Scope.REQUEST)
    results: list[_PersistentBroker] = []
    worker = threading.Thread(target=lambda: results.append(child.resolve(_PersistentBroker)), daemon=True)
    with cache_item(root, _AppBrokerGroup.broker).lock:
        worker.start()
        worker.join(timeout=5)
        finished_while_held = not worker.is_alive()
    worker.join(timeout=5)
    assert finished_while_held
    assert results[0] is warm


def test_private_scope_map_backs_find_container() -> None:
    root = Container()
    child = root.build_child_container(scope=Scope.REQUEST)

    # The map holds ancestors only — never the container itself, which would be a reference cycle.
    # `find_container` short-circuits on its own scope, so a self-entry would be dead weight.
    assert set(child._scope_map) == {Scope.APP}
    assert child._scope_map[Scope.APP] is root
    assert root._scope_map == {}
    assert child.find_container(Scope.REQUEST) is child  # own scope still resolves
    assert child.find_container(Scope.APP) is root


def test_closed_children_are_freed_without_the_cycle_collector() -> None:
    # A container must not reference itself: a self-reference makes every container cyclic garbage,
    # so a request-scoped app produces work for the collector at its request rate. Asserts the
    # property that matters (reclaimable by refcount alone), not the shape of the map behind it.
    class Sentinel:  # rides in each child's context so liveness is observable
        pass

    freed = 0

    def _count(_: object) -> None:
        nonlocal freed
        freed += 1

    n_children = 100
    root = Container(scope=Scope.APP)
    gc.collect()
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        children = []
        for _ in range(n_children):
            sentinel = Sentinel()
            child = root.build_child_container(scope=Scope.REQUEST, context={Sentinel: sentinel})
            weakref.finalize(sentinel, _count, None)
            child.close_sync()
            children.append(child)
        del children, child, sentinel
        # Both halves matter: the children really did become garbage (freed == n_children), AND
        # refcounting alone reclaimed them, leaving the cycle collector nothing to do.
        assert freed == n_children
        assert gc.collect() == 0
    finally:
        if was_enabled:
            gc.enable()


def test_add_providers_registers_and_resolves_by_type_and_reference() -> None:
    container = Container(scope=Scope.APP)
    str_factory = providers.Factory(creator=lambda: "added", bound_type=str)

    container.add_providers(str_factory)

    assert container.resolve(str) == "added"
    assert container.resolve_provider(str_factory) == "added"


def test_add_providers_raises_on_duplicate_against_registered() -> None:
    str_factory = providers.Factory(creator=lambda: "one", bound_type=str)
    other_str_factory = providers.Factory(creator=lambda: "two", bound_type=str)
    container = Container(scope=Scope.APP)
    container.add_providers(str_factory)

    with pytest.raises(DuplicateProviderTypeError) as exc:
        container.add_providers(other_str_factory)
    assert exc.value.provider_type is str


def test_add_providers_raises_on_duplicate_intra_batch() -> None:
    str_factory = providers.Factory(creator=lambda: "one", bound_type=str)
    other_str_factory = providers.Factory(creator=lambda: "two", bound_type=str)
    container = Container(scope=Scope.APP)

    with pytest.raises(DuplicateProviderTypeError) as exc:
        container.add_providers(str_factory, other_str_factory)
    assert exc.value.provider_type is str


def test_add_providers_on_child_container_raises() -> None:
    root = Container(scope=Scope.APP)
    child = root.build_child_container(scope=Scope.REQUEST)
    str_factory = providers.Factory(creator=lambda: "added", bound_type=str)

    with pytest.raises(ChildContainerRegistrationError, match="root") as exc:
        child.add_providers(str_factory)
    assert isinstance(exc.value, exceptions.RegistrationError)
    assert exc.value.container_scope is Scope.REQUEST


def test_find_provider_returns_registered_provider_or_none() -> None:
    root = Container(scope=Scope.APP, groups=[_AppBrokerGroup])
    child = root.build_child_container(scope=Scope.REQUEST)

    assert root.find_provider(_PersistentBroker) is _AppBrokerGroup.broker
    assert child.find_provider(_PersistentBroker) is _AppBrokerGroup.broker
    assert root.find_provider(str) is None


def test_closed_is_read_only() -> None:
    container = Container(scope=Scope.APP)
    with pytest.raises(AttributeError):
        container.closed = True  # ty: ignore[invalid-assignment]
    assert container.closed is False


def test_registries_are_not_public() -> None:
    container = Container(scope=Scope.APP)
    for name in ("providers_registry", "cache_registry", "context_registry", "overrides_registry"):
        assert not hasattr(container, name)


def test_resolve_dependency_with_provider_returns_same_instance_as_resolve_provider() -> None:
    class G(Group):
        cached = providers.Factory(creator=lambda: "value", bound_type=str, cache=True)

    container = Container(groups=[G])
    via_dispatch = container.resolve_dependency(G.cached)
    via_resolve_provider = container.resolve_provider(G.cached)
    assert via_dispatch is via_resolve_provider


def test_add_providers_rebuilds_stale_wiring_plan_for_optional_dependency() -> None:
    """A memoized WiringPlan built before `add_providers` must not keep an optional dep as None."""

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Inner:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Outer:
        inner: Inner | None = None

    container = Container(scope=Scope.APP)
    outer_factory = providers.Factory(creator=Outer)  # not cached: second resolve rebuilds

    first = container.resolve_provider(outer_factory)
    assert first.inner is None

    container.add_providers(providers.Factory(creator=Inner))

    second = container.resolve_provider(outer_factory)
    assert isinstance(second.inner, Inner)


def test_add_providers_rebuilds_stale_wiring_plan_for_required_dependency() -> None:
    """A memoized WiringPlan that recorded a required dep as unwireable must retry after registration."""

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Inner:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Outer:
        inner: Inner

    container = Container(scope=Scope.APP)
    outer_factory = providers.Factory(creator=Outer)

    with pytest.raises(ArgumentResolutionError):
        container.resolve_provider(outer_factory)

    container.add_providers(providers.Factory(creator=Inner))

    result = container.resolve_provider(outer_factory)
    assert isinstance(result.inner, Inner)


def test_add_providers_on_closed_root_registers_fine() -> None:
    """Ruled: no closed-state check on add_providers — registering on a closed root just works."""
    container = Container(scope=Scope.APP)
    container.close_sync()
    str_factory = providers.Factory(creator=lambda: "added", bound_type=str)

    container.add_providers(str_factory)  # no ContainerClosedError: registration doesn't touch closed state

    with pytest.raises(ContainerClosedError):
        container.resolve(str)
    container.open()
    assert container.resolve(str) == "added"


def test_resolve_dependency_with_type_returns_same_instance_as_resolve() -> None:
    class G(Group):
        cached = providers.Factory(creator=lambda: "value", bound_type=str, cache=True)

    container = Container(groups=[G])
    via_dispatch = container.resolve_dependency(str)
    via_resolve = container.resolve(str)
    assert via_dispatch is via_resolve


def test_resolve_dependency_with_provider_returns_override() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        name: str = "original"

    class G(Group):
        app_factory = providers.Factory(creator=Service)

    container = Container(groups=[G])
    override = Service(name="override")
    container.override(G.app_factory, override)

    assert container.resolve_dependency(G.app_factory) is override


def test_resolve_dependency_with_unregistered_type_raises_with_suggestion() -> None:
    class Database:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class PostgresDatabase(Database):
        pass

    class G(Group):
        db = providers.Factory(creator=PostgresDatabase)

    container = Container(groups=[G])
    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        container.resolve_dependency(Database)

    exc = exc_info.value
    assert exc.dependency_type is Database
    assert exc.suggestions == [
        suggester.Suggestion(name="PostgresDatabase", reason="registered subclass", scope=Scope.APP)
    ]


def test_resolve_dependency_works_on_child_container_for_both_arms() -> None:
    class G(Group):
        request_factory = providers.Factory(scope=Scope.REQUEST, creator=lambda: "value", bound_type=str)

    app_container = Container(groups=[G])
    request_container = app_container.build_child_container(scope=Scope.REQUEST)

    assert request_container.resolve_dependency(str) == "value"
    assert request_container.resolve_dependency(G.request_factory) == "value"


class _OverrideSvc: ...


class _OverrideGroup(Group):
    svc = providers.Factory(_OverrideSvc)


def test_override_context_manager_applies_and_resets() -> None:
    container = Container(groups=[_OverrideGroup])
    mock = _OverrideSvc()
    with container.override(_OverrideGroup.svc, mock) as bound:
        assert bound is mock
        assert container.resolve(_OverrideSvc) is mock
    assert container.resolve(_OverrideSvc) is not mock


def test_override_context_manager_restores_prior_imperative_override() -> None:
    container = Container(groups=[_OverrideGroup])
    first = _OverrideSvc()
    second = _OverrideSvc()
    container.override(_OverrideGroup.svc, first)
    with container.override(_OverrideGroup.svc, second):
        assert container.resolve(_OverrideSvc) is second
    assert container.resolve(_OverrideSvc) is first


def test_override_context_manager_nested_unwinds_in_order() -> None:
    container = Container(groups=[_OverrideGroup])
    outer = _OverrideSvc()
    inner = _OverrideSvc()
    with container.override(_OverrideGroup.svc, outer):
        with container.override(_OverrideGroup.svc, inner):
            assert container.resolve(_OverrideSvc) is inner
        assert container.resolve(_OverrideSvc) is outer
    resolved = container.resolve(_OverrideSvc)
    assert resolved is not outer
    assert resolved is not inner


def test_override_context_manager_restores_on_exception() -> None:
    container = Container(groups=[_OverrideGroup])
    mock = _OverrideSvc()
    msg = "boom"
    with pytest.raises(RuntimeError), container.override(_OverrideGroup.svc, mock):
        raise RuntimeError(msg)
    assert container.resolve(_OverrideSvc) is not mock


def test_override_context_manager_exit_restores_snapshot_after_inner_reset() -> None:
    container = Container(groups=[_OverrideGroup])
    first = _OverrideSvc()
    second = _OverrideSvc()
    container.override(_OverrideGroup.svc, first)
    with container.override(_OverrideGroup.svc, second):
        container.reset_override(_OverrideGroup.svc)
        assert container.resolve(_OverrideSvc) is not first
        assert container.resolve(_OverrideSvc) is not second
    assert container.resolve(_OverrideSvc) is first  # exit restores the snapshot taken at override() time


def test_override_survives_root_close_sync_and_reopen() -> None:
    container = Container(groups=[_OverrideGroup])
    mock = _OverrideSvc()
    container.override(_OverrideGroup.svc, mock)
    container.close_sync()
    container.open()
    assert container.resolve(_OverrideSvc) is mock


async def test_override_survives_root_close_async_and_reopen() -> None:
    container = Container(groups=[_OverrideGroup])
    mock = _OverrideSvc()
    container.override(_OverrideGroup.svc, mock)
    await container.close_async()
    container.open()
    assert container.resolve(_OverrideSvc) is mock


def test_override_context_manager_exit_after_root_close_restores_prior_override() -> None:
    container = Container(groups=[_OverrideGroup])
    first = _OverrideSvc()
    second = _OverrideSvc()
    container.override(_OverrideGroup.svc, first)
    with container.override(_OverrideGroup.svc, second):
        container.close_sync()
        container.open()
        assert container.resolve(_OverrideSvc) is second
    assert container.resolve(_OverrideSvc) is first


def test_resolve_provider_raises_for_unhandled_provider_type() -> None:
    # Every real provider type compiles; an unknown AbstractProvider subclass hits compile_resolver's
    # final explicit raise (the single place a new, unregistered provider type is rejected).
    class _UnknownProvider(AbstractProvider[object]):
        __slots__ = ()

    provider = _UnknownProvider(scope=Scope.APP, bound_type=None)
    container = Container()
    with pytest.raises(TypeError, match="no compiled resolver for provider type _UnknownProvider"):
        container.resolve_provider(provider)


def test_abstract_provider_is_a_plain_class() -> None:
    """`resolve_dependency` runs `isinstance(x, AbstractProvider)` per call; ABCMeta would make it Python-level."""
    assert type(AbstractProvider) is type


# --- validate() is the only trigger: construction, open(), resolve() and add_providers() never ----
# --- walk the graph on their own. -------------------------------------------------------------


@dataclasses.dataclass(kw_only=True, slots=True)
class _DeferMissing:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class _DeferBrokenService:
    missing: _DeferMissing  # no provider registered for _DeferMissing -> validation fails


class _DeferBrokenGroup(Group):
    svc = providers.Factory(creator=_DeferBrokenService)


class _DeferRequest: ...


@dataclasses.dataclass(kw_only=True, slots=True)
class _DeferReqDependent:
    request: _DeferRequest


class _DeferFactoryNeedingRequestGroup(Group):
    # Depends by-type on _DeferRequest, whose ContextProvider an integration registers after construction.
    dependent = providers.Factory(creator=_DeferReqDependent)


def test_construction_never_validates() -> None:
    """INVARIANT: `validate()` is the only thing that walks the graph.

    Constructing a container from a cyclic group raises nothing; only the later `validate()` call
    surfaces `ValidationFailedError`. An `__init__` that walked eagerly is the split-validation
    machinery "Validation is explicit" (docs/introduction/design-decisions.md) discarded.
    """
    container = Container(scope=Scope.APP, groups=[CycleGroup])  # a cycle: no raise here any more
    with pytest.raises(ValidationFailedError):
        container.validate()


def test_add_providers_never_validates_and_does_not_roll_back() -> None:
    """INVARIANT: `validate()` is the only thing that walks the graph.

    `add_providers` registers `Broken` quietly -- no raise, no rollback -- even onto a registry
    already marked validated; only the next explicit `validate()` call surfaces
    `ValidationFailedError`. An `add_providers` that walked eagerly is the rollback path
    "Validation is explicit" (docs/introduction/design-decisions.md) discarded.
    """

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing: ...

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Broken:
        missing: Missing

    container = Container(scope=Scope.APP)
    container.validate()  # clean, marks the registry validated
    broken = providers.Factory(creator=Broken)

    container.add_providers(broken)  # registers quietly: no raise, no rollback

    assert container.find_provider(Broken) is broken
    with pytest.raises(ValidationFailedError):
        container.validate()


def test_open_never_validates() -> None:
    """INVARIANT: `validate()` is the only thing that walks the graph.

    `open()` on a cyclic graph raises nothing, neither called directly nor entered via the context
    manager. Binding validation to `open()` was 3.0's design, discarded per "Validation is
    explicit" (docs/introduction/design-decisions.md) after the root's open hook not firing in
    some execution contexts caused six production defects.
    """
    container = Container(scope=Scope.APP, groups=[CycleGroup])
    container.open()  # no raise
    with container:  # nor via the context manager
        pass


def test_resolve_never_validates() -> None:
    """INVARIANT: `validate()` is the only thing that walks the graph.

    Resolving `_DeferBrokenService` on an unvalidated broken graph raises `ArgumentResolutionError`
    for the one missing dependency, not `ValidationFailedError` for the whole graph -- proving
    `resolve()` never walks looking for other errors. Making it validate first is the per-resolve
    tax "Validation is explicit" (docs/introduction/design-decisions.md) rejected.
    """
    container = Container(scope=Scope.APP, groups=[_DeferBrokenGroup])
    with pytest.raises(ArgumentResolutionError):
        container.resolve(_DeferBrokenService)


@pytest.mark.parametrize("validate", [True, False])
def test_validate_argument_is_rejected(validate: bool) -> None:
    with pytest.raises(TypeError, match="validate"):
        Container(scope=Scope.APP, validate=validate)  # ty: ignore[unknown-argument]


@pytest.mark.parametrize(
    "name", ["ValidateArgumentWarning", "ContextValueNoneWarning", "UnvalidatedContainerWarning", "DependencyPathMixin"]
)
def test_removed_name_is_not_exported(name: str) -> None:
    assert not hasattr(exceptions, name)
    assert name not in exceptions.__all__


@pytest.mark.parametrize("name", ["SUGGESTION_HEADER"])
def test_internal_helper_is_not_exported(name: str) -> None:
    assert not hasattr(exceptions, name)
    assert name not in exceptions.__all__


@pytest.mark.parametrize("name", ["scope_map", "lock"])
def test_removed_public_alias_is_gone(name: str) -> None:
    assert not hasattr(Container(), name)


def test_integration_pattern_context_registered_after_construction() -> None:
    # An integration may register a ContextProvider after construction; validate(), called once the
    # graph is complete, finds it clean.
    container = Container(scope=Scope.APP, groups=[_DeferFactoryNeedingRequestGroup])  # no raise
    container.add_providers(providers.ContextProvider(_DeferRequest))  # integration wires it in
    container.validate()  # graph now complete -> validates clean
    with container:
        pass


def test_add_providers_completed_graph_resolves_without_an_explicit_open() -> None:
    # add_providers never validates, but resolve still prepares the container implicitly.
    container = Container(
        scope=Scope.APP,
        groups=[_DeferFactoryNeedingRequestGroup],
        context={_DeferRequest: _DeferRequest()},
    )
    container.add_providers(providers.ContextProvider(_DeferRequest))  # integration wires it in
    request = container.build_child_container(scope=Scope.REQUEST)
    assert isinstance(request.resolve(_DeferReqDependent), _DeferReqDependent)  # no explicit open()
    assert container.closed is False


_OrderId = typing.NewType("_OrderId", int)


def test_resolve_and_find_provider_by_newtype() -> None:
    factory = providers.Factory(lambda: _OrderId(3), bound_type=_OrderId)
    container = Container()
    container.add_providers(factory)
    assert container.resolve(_OrderId) == _OrderId(3)
    assert container.resolve_dependency(_OrderId) == _OrderId(3)
    assert container.find_provider(_OrderId) is factory
