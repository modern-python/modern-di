import copy
import dataclasses
import gc
import inspect
import os
import typing
import warnings
import weakref

import pytest

from modern_di import Container, Group, Scope, exceptions, providers, suggester
from modern_di import container as container_module
from modern_di.exceptions import (
    ArgumentResolutionError,
    ChildContainerRegistrationError,
    CircularDependencyError,
    ContainerClosedError,
    ContainerClosedWarning,
    DuplicateProviderTypeError,
    InvalidChildScopeError,
    InvalidScopeDependencyError,
    InvalidScopeTypeError,
    MaxScopeReachedError,
    ProviderNotRegisteredError,
    ScopeSkippedError,
    ValidateArgumentWarning,
    ValidationFailedError,
)
from modern_di.providers.abstract import AbstractProvider


def test_container_prevent_copy() -> None:
    container = Container()
    container_deepcopy = copy.deepcopy(container)
    container_copy = copy.copy(container)
    assert container_deepcopy is container_copy is container


def test_container_scope_skipped() -> None:
    app_factory = providers.Factory(creator=lambda: "test")
    container = Container(scope=Scope.REQUEST)
    container.open()
    with pytest.raises(ScopeSkippedError, match=r"No APP-scope container exists in this chain") as exc:
        container.resolve_provider(app_factory)
    assert exc.value.provider_scope == Scope.APP


def test_container_build_child() -> None:
    app_container = Container()
    app_container.open()
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    assert request_container.scope == Scope.REQUEST
    assert app_container.scope == Scope.APP


def test_container_scope_limit_reached() -> None:
    step_container = Container(scope=Scope.STEP)
    step_container.open()
    with pytest.raises(MaxScopeReachedError, match=r"Max scope of STEP is reached.") as exc:
        step_container.build_child_container()
    assert exc.value.parent_scope == Scope.STEP


def test_container_build_child_wrong_scope() -> None:
    app_container = Container()
    app_container.open()
    with pytest.raises(InvalidChildScopeError, match="Scope of child container cannot be") as exc:
        app_container.build_child_container(scope=Scope.APP)
    assert exc.value.parent_scope == Scope.APP
    assert exc.value.child_scope == Scope.APP


def test_container_resolve_missing_provider() -> None:
    app_container = Container()
    with pytest.raises(
        ProviderNotRegisteredError,
        match=r"Provider of type <class 'str'> is not registered in providers registry.",
    ) as exc:
        app_container.resolve(str)
    assert exc.value.provider_type is str


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
    container.open()
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
    rendered = str(exc_info.value)
    lineno = inspect.getsourcelines(CycleA)[1]
    assert f"({CycleA.__module__}:{lineno})" in rendered


def test_validate_detects_cycle() -> None:
    container = Container(groups=[CycleGroup])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.errors
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


def test_validate_memoizes_diamond() -> None:
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

    call_count = 0

    class _CountingFactory(providers.Factory[Bottom]):
        __slots__ = ()

        def get_dependencies(self, container: Container) -> dict[str, AbstractProvider[typing.Any]]:
            nonlocal call_count
            call_count += 1
            return super().get_dependencies(container)

    bottom_provider = _CountingFactory(creator=Bottom)

    class DiamondGroup(Group):
        bottom = bottom_provider
        left = providers.Factory(creator=Left)
        right = providers.Factory(creator=Right)
        top = providers.Factory(creator=Top)

    container = Container(groups=[DiamondGroup])
    container.validate()
    assert call_count == 1


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
    [issue] = exc.value.errors
    assert isinstance(issue, InvalidScopeDependencyError)
    assert issue.parameter_name == "inner"
    assert issue.provider.scope == Scope.APP
    assert issue.dep_provider.scope == Scope.REQUEST


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
    container.providers_registry.add_providers(inner, outer)

    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    [issue] = exc.value.errors
    assert isinstance(issue, InvalidScopeDependencyError)
    assert issue.parameter_name == "inner"
    assert issue.provider.scope == Scope.APP
    assert issue.dep_provider.scope == Scope.REQUEST


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
    [issue] = exc.value.errors
    assert isinstance(issue, ArgumentResolutionError)
    assert issue.arg_name == "missing"


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
    error_types = {type(e) for e in exc.value.errors}
    assert InvalidScopeDependencyError in error_types
    assert ArgumentResolutionError in error_types
    assert CircularDependencyError in error_types


def test_walk_errors_returns_flat_list_in_walk_order() -> None:
    class _Missing: ...

    @dataclasses.dataclass(kw_only=True, slots=True)
    class _NeedsMissing:
        missing: _Missing

    class G(Group):
        a = providers.Factory(creator=CycleA)
        b = providers.Factory(creator=CycleB)
        svc = providers.Factory(creator=_NeedsMissing)

    container = Container(scope=Scope.APP, groups=[G])
    errors = container._walk_errors()

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
    [issue] = exc.value.errors
    assert isinstance(issue, CircularDependencyError)


def test_validate_handles_factory_with_static_kwargs() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        name: str

    class G(Group):
        svc = providers.Factory(creator=Service, kwargs={"name": "static"})

    Container(groups=[G]).validate()  # must not raise


def test_validation_failed_error_str_renders_inner_errors() -> None:
    container = Container(groups=[CycleGroup])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    rendered = str(exc.value)
    assert "found 1 issue(s)" in rendered
    assert "Circular dependency detected" in rendered


def test_build_child_container_propagates_use_lock_false() -> None:
    root = Container(use_lock=False)
    root.open()
    child = root.build_child_container(scope=Scope.REQUEST)
    assert root._lock is None
    assert child._lock is None


def test_container_provider_resolves_on_subclasses() -> None:
    class MyContainer(Container):
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        di_container: Container

    class G(Group):
        svc = providers.Factory(creator=Service)

    container = MyContainer(groups=[G])
    container.open()
    instance = container.resolve(Service)
    assert instance.di_container is container


def test_container_rejects_non_intenum_scope_at_init() -> None:
    with pytest.raises(InvalidScopeTypeError) as exc:
        Container(scope=99)  # ty: ignore[invalid-argument-type]
    assert "99" in str(exc.value)


def test_constructor_rejects_parent_with_non_increasing_scope() -> None:
    app = Container(scope=Scope.APP)
    app.open()
    with pytest.raises(InvalidChildScopeError):
        Container(scope=Scope.APP, parent_container=app)
    request = app.build_child_container(scope=Scope.REQUEST)
    with pytest.raises(InvalidChildScopeError):
        Container(scope=Scope.APP, parent_container=request)


def test_resolve_on_closed_container_warns() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        assert container.resolve(Container) is container
    assert container.closed is False  # self-healed: reopened by the warning path


def test_reenter_reopens_closed_container() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with container:  # __enter__ -> open() clears closed
        assert container.resolve(Container) is container


async def test_closed_container_async_path_warns() -> None:
    container = Container(scope=Scope.APP)
    await container.close_async()
    with pytest.warns(ContainerClosedWarning):
        assert container.resolve(Container) is container


class _PersistentBroker: ...


class _AppBrokerGroup(Group):
    broker = providers.Factory(
        scope=Scope.APP, creator=_PersistentBroker, cache=providers.CacheSettings(clear_cache=False)
    )


def test_resolving_through_closed_parent_via_open_child_warns() -> None:
    app = Container(scope=Scope.APP, groups=[_AppBrokerGroup])
    app.open()
    child = app.build_child_container(scope=Scope.REQUEST)
    child.open()
    app.close_sync()
    with pytest.warns(ContainerClosedWarning):
        assert isinstance(child.resolve(_PersistentBroker), _PersistentBroker)


async def test_async_context_manager_reopens() -> None:
    container = Container(scope=Scope.APP)
    async with container:
        pass
    with pytest.warns(ContainerClosedWarning):
        container.resolve(Container)
    async with container:
        assert container.resolve(Container) is container


def test_open_reopens_closed_container() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        container.resolve(Container)
    container.open()
    assert container.resolve(Container) is container
    assert container.build_child_container(scope=Scope.REQUEST).scope is Scope.REQUEST


def test_reuse_after_close_warns_and_reopens() -> None:
    container = Container(scope=Scope.APP)
    container.open()
    container.close_sync()
    with pytest.warns(ContainerClosedWarning) as record:
        assert container.resolve(Container) is container
    assert container.closed is False
    assert record[0].message.container_scope is Scope.APP  # ty: ignore[unresolved-attribute]


def test_reuse_warning_points_at_caller_not_library() -> None:
    container = Container(scope=Scope.APP)
    container.open()
    container.close_sync()
    with pytest.warns(ContainerClosedWarning) as record:
        container.resolve(Container)
    assert record[0].filename == __file__


def test_explicit_open_after_close_does_not_warn() -> None:
    container = Container(scope=Scope.APP)
    container.open()
    container.close_sync()
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a deliberate reopen is silent
        container.open()
        assert container.resolve(Container) is container


def test_child_built_off_closed_parent_warns_only_when_the_parent_resolves() -> None:
    """INVARIANT: building a child container does not require the parent to be open.

    `build_child_container` reads the parent's scope map and its two shared registries; it resolves
    nothing and touches no cache, so there is deliberately no closed-check on the parent. Adding one
    would break every integration that builds a request child after a shutdown/restart cycle.
    """
    app = Container(scope=Scope.APP, groups=[_AppBrokerGroup])
    app.open()
    app.close_sync()
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # parenting alone touches no closed state
        child = app.build_child_container(scope=Scope.REQUEST)
    with pytest.warns(ContainerClosedWarning):
        child.resolve(_PersistentBroker)  # navigates to the closed APP owner


def test_caller_stacklevel_does_not_skip_sibling_packages() -> None:
    # `modern_di_fastapi/` is a *sibling* of `modern_di/`, not part of it: a warning raised through
    # an integration must stop at the integration, not walk past it into framework code. Driven with
    # a synthesized frame so the test needs no sibling package installed.
    package_dir = container_module._PACKAGE_DIR
    sibling = f"{package_dir.rstrip(os.sep)}_fastapi{os.sep}routing.py"
    namespace: dict[str, typing.Any] = {}
    exec(compile("def integration(fn):\n    return fn()\n", sibling, "exec"), namespace)  # noqa: S102
    assert namespace["integration"](container_module._caller_stacklevel) == 1


def test_container_closed_warning_message() -> None:
    warning = ContainerClosedWarning(container_scope=Scope.REQUEST)
    assert warning.container_scope is Scope.REQUEST
    assert "reused after close" in str(warning)
    assert "open()" in str(warning)


def test_container_closed_error_message_and_attr() -> None:
    """Back-compat pin: nothing raises this class anymore, so this test is what keeps it covered."""
    err = ContainerClosedError(container_scope=Scope.APP)
    assert err.container_scope is Scope.APP
    assert "not open" in str(err)
    assert "open()" in str(err)


def test_open_on_open_container_is_noop() -> None:
    with Container(scope=Scope.APP) as container:
        container.open()
        assert container.closed is False
        assert container.resolve(Container) is container


# --- a container is open from construction ------------------------------------------------------


def test_fresh_container_is_open() -> None:
    container = Container(scope=Scope.APP)
    assert container.closed is False


def test_construct_then_close_then_reuse_warns_once() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        assert container.resolve(Container) is container
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # reopened: the second resolve is silent
        assert container.resolve(Container) is container


def test_fresh_container_resolves_without_open() -> None:
    container = Container(scope=Scope.APP)
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a never-closed container must not warn
        assert container.resolve(Container) is container
    assert container.closed is False


def test_fresh_container_builds_child_and_child_resolves_without_open() -> None:
    app = Container(scope=Scope.APP)
    child = app.build_child_container(scope=Scope.REQUEST)
    assert child.resolve(Container) is child
    assert app.closed is False  # building a child does not close the parent


def test_build_child_off_closed_parent_is_allowed() -> None:
    app = Container(scope=Scope.APP)
    app.open()
    app.close_sync()
    child = app.build_child_container(scope=Scope.REQUEST)  # no raise: builds nothing, resolves nothing
    assert child.scope is Scope.REQUEST


def test_private_lock_and_scope_map_back_the_machinery() -> None:
    root = Container(use_lock=True)
    root.open()
    child = root.build_child_container(scope=Scope.REQUEST)

    # _lock is a reentrant lock (threading.RLock is a factory, not a type, so
    # assert behavior, not isinstance)
    assert root._lock is not None
    assert root._lock.acquire()
    assert root._lock.acquire()  # reentrant
    root._lock.release()
    root._lock.release()
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
    root.open()
    gc.collect()
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        children = []
        for _ in range(n_children):
            sentinel = Sentinel()
            child = root.build_child_container(scope=Scope.REQUEST, context={Sentinel: sentinel})
            weakref.finalize(sentinel, _count, None)
            child.open()
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


def test_use_lock_false_yields_no_private_lock() -> None:
    root = Container(use_lock=False)
    root.open()
    child = root.build_child_container(scope=Scope.REQUEST)
    assert root._lock is None
    assert child._lock is None


def test_scope_map_alias_warns_and_forwards() -> None:
    container = Container()
    with pytest.warns(DeprecationWarning, match="scope_map"):
        aliased = container.scope_map
    assert aliased is container._scope_map


def test_lock_alias_warns_and_forwards() -> None:
    container = Container(use_lock=True)
    with pytest.warns(DeprecationWarning, match="lock"):
        aliased = container.lock
    assert aliased is container._lock


def test_resolve_emits_no_deprecation_warning() -> None:
    class _Dep:
        pass

    class _Group(Group):
        dep = providers.Factory(scope=Scope.APP, creator=_Dep, cache=True)

    container = Container(groups=[_Group])
    container.open()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        container.resolve(_Dep)  # touches _lock and _scope_map internally
        container.build_child_container(scope=Scope.REQUEST)


def test_add_providers_registers_and_resolves_by_type_and_reference() -> None:
    container = Container(scope=Scope.APP)
    container.open()
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
    root.open()
    child = root.build_child_container(scope=Scope.REQUEST)
    str_factory = providers.Factory(creator=lambda: "added", bound_type=str)

    with pytest.raises(ChildContainerRegistrationError, match="root") as exc:
        child.add_providers(str_factory)
    assert isinstance(exc.value, exceptions.RegistrationError)
    assert exc.value.scope is Scope.REQUEST


def test_resolve_dependency_with_provider_returns_same_instance_as_resolve_provider() -> None:
    class G(Group):
        cached = providers.Factory(creator=lambda: "value", bound_type=str, cache=True)

    container = Container(groups=[G])
    container.open()
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
    container.open()
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
    container.open()
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

    with pytest.warns(ContainerClosedWarning):
        assert container.resolve(str) == "added"


def test_resolve_dependency_with_type_returns_same_instance_as_resolve() -> None:
    class G(Group):
        cached = providers.Factory(creator=lambda: "value", bound_type=str, cache=True)

    container = Container(groups=[G])
    container.open()
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
    container.open()
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
    assert exc.provider_type is Database
    assert exc.suggestions == [
        suggester.Suggestion(name="PostgresDatabase", reason="registered subclass", scope=Scope.APP)
    ]


def test_resolve_dependency_works_on_child_container_for_both_arms() -> None:
    class G(Group):
        request_factory = providers.Factory(scope=Scope.REQUEST, creator=lambda: "value", bound_type=str)

    app_container = Container(groups=[G])
    app_container.open()
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    request_container.open()

    assert request_container.resolve_dependency(str) == "value"
    assert request_container.resolve_dependency(G.request_factory) == "value"


class _OverrideSvc: ...


class _OverrideGroup(Group):
    svc = providers.Factory(_OverrideSvc)


def test_override_context_manager_applies_and_resets() -> None:
    container = Container(groups=[_OverrideGroup])
    container.open()
    mock = _OverrideSvc()
    with container.override(_OverrideGroup.svc, mock) as bound:
        assert bound is mock
        assert container.resolve(_OverrideSvc) is mock
    assert container.resolve(_OverrideSvc) is not mock


def test_override_context_manager_restores_prior_imperative_override() -> None:
    container = Container(groups=[_OverrideGroup])
    container.open()
    first = _OverrideSvc()
    second = _OverrideSvc()
    container.override(_OverrideGroup.svc, first)
    with container.override(_OverrideGroup.svc, second):
        assert container.resolve(_OverrideSvc) is second
    assert container.resolve(_OverrideSvc) is first


def test_override_context_manager_nested_unwinds_in_order() -> None:
    container = Container(groups=[_OverrideGroup])
    container.open()
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
    container.open()
    mock = _OverrideSvc()
    msg = "boom"
    with pytest.raises(RuntimeError), container.override(_OverrideGroup.svc, mock):
        raise RuntimeError(msg)
    assert container.resolve(_OverrideSvc) is not mock


def test_override_context_manager_exit_restores_snapshot_after_inner_reset() -> None:
    container = Container(groups=[_OverrideGroup])
    container.open()
    first = _OverrideSvc()
    second = _OverrideSvc()
    container.override(_OverrideGroup.svc, first)
    with container.override(_OverrideGroup.svc, second):
        container.reset_override(_OverrideGroup.svc)
        assert container.resolve(_OverrideSvc) is not first
        assert container.resolve(_OverrideSvc) is not second
    assert container.resolve(_OverrideSvc) is first  # exit restores the snapshot taken at override() time


def test_resolve_provider_raises_for_unhandled_provider_type() -> None:
    # Every real provider type compiles; an unknown AbstractProvider subclass hits compile_resolver's
    # final explicit raise (the single place a new, unregistered provider type is rejected).
    class _UnknownProvider(AbstractProvider[object]):
        __slots__ = ()

    provider = _UnknownProvider(scope=Scope.APP, bound_type=None)
    container = Container()
    container.open()
    with pytest.raises(TypeError, match="no compiled resolver for provider type _UnknownProvider"):
        container.resolve_provider(provider)


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
    container = Container(scope=Scope.APP, groups=[CycleGroup])  # a cycle: no raise here any more
    with pytest.raises(ValidationFailedError):
        container.validate()


def test_add_providers_never_validates_and_does_not_roll_back() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing: ...

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Broken:
        missing: Missing

    container = Container(scope=Scope.APP)
    container.validate()  # clean, marks the registry validated
    broken = providers.Factory(creator=Broken)

    container.add_providers(broken)  # registers quietly: no raise, no rollback

    assert container.providers_registry.find_provider(Broken) is broken
    with pytest.raises(ValidationFailedError):
        container.validate()


def test_open_never_validates() -> None:
    container = Container(scope=Scope.APP, groups=[CycleGroup])
    container.open()  # no raise
    with container:  # nor via the context manager
        pass


def test_resolve_never_validates() -> None:
    # A broken graph surfaces at the resolve that hits it, not as an aggregate.
    container = Container(scope=Scope.APP, groups=[_DeferBrokenGroup])
    with pytest.raises(ArgumentResolutionError):
        container.resolve(_DeferBrokenService)


def test_validate_argument_is_a_deprecated_no_op() -> None:
    with pytest.warns(ValidateArgumentWarning) as record:
        container = Container(scope=Scope.APP, groups=[CycleGroup], validate=True)
    assert "validate()" in str(record[0].message)
    with pytest.raises(ValidationFailedError):
        container.validate()  # the argument changed nothing


def test_validate_false_also_warns_and_changes_nothing() -> None:
    with pytest.warns(ValidateArgumentWarning):
        Container(scope=Scope.APP, validate=False)


def test_no_warning_when_validate_is_not_passed() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        Container(scope=Scope.APP)


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
