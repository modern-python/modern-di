import copy
import dataclasses
import inspect
import os
import typing
import warnings

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


def test_cycle_raises_at_construction() -> None:
    # Monotone: registering more providers can only add a cycle, never remove one, so it is
    # safe to raise before the graph is complete.
    with pytest.raises(ValidationFailedError) as exc:
        Container(scope=Scope.APP, groups=[CycleGroup], validate=True)
    [issue] = exc.value.errors
    assert isinstance(issue, CircularDependencyError)


def test_cycle_path_carries_definition_sites() -> None:
    with pytest.raises(ValidationFailedError) as exc_info:
        Container(groups=[CycleGroup], validate=True)  # monotone: raises at construction
    rendered = str(exc_info.value)
    lineno = inspect.getsourcelines(CycleA)[1]
    assert f"({CycleA.__module__}:{lineno})" in rendered


def test_validate_detects_cycle() -> None:
    # validate=False: exercise validate() directly rather than the construction-time raise.
    container = Container(groups=[CycleGroup], validate=False)
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

    Container(groups=[G], validate=True).open()  # deferred validation runs at entry; must not raise


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

    # validate=False: exercise validate() directly rather than the construction-time raise.
    container = Container(groups=[G], validate=False)
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

    container = Container(validate=False)
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

    # validate=False: a construction-time raise would only surface the monotone half (cycle,
    # inverted scope); validate() walks and reports the completeness half (missing dep) too.
    container = Container(groups=[G], validate=False)
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    error_types = {type(e) for e in exc.value.errors}
    assert InvalidScopeDependencyError in error_types
    assert ArgumentResolutionError in error_types
    assert CircularDependencyError in error_types


def test_walk_errors_partitions_monotone_from_completeness() -> None:
    # Cycles and inverted scopes are monotone (registering more providers can only add them);
    # missing dependencies are not, so they are classified separately.
    class _Missing: ...

    @dataclasses.dataclass(kw_only=True, slots=True)
    class _NeedsMissing:
        missing: _Missing

    class G(Group):
        a = providers.Factory(creator=CycleA)
        b = providers.Factory(creator=CycleB)
        svc = providers.Factory(creator=_NeedsMissing)

    container = Container(scope=Scope.APP, groups=[G], validate=False)
    walked = container._walk_errors()  # noqa: SLF001

    monotone = [type(error).__name__ for is_monotone, error in walked if is_monotone]
    completeness = [type(error).__name__ for is_monotone, error in walked if not is_monotone]
    assert monotone == ["CircularDependencyError"]
    assert completeness == ["ArgumentResolutionError"]


def test_validate_detects_cycle_across_scopes() -> None:
    class CrossScopeCycleGroup(Group):
        a = providers.Factory(scope=Scope.REQUEST, creator=CycleA)
        b = providers.Factory(scope=Scope.REQUEST, creator=CycleB)

    # validate=False: exercise validate() directly rather than the construction-time raise.
    container = Container(groups=[CrossScopeCycleGroup], validate=False)
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

    Container(groups=[G], validate=True).open()  # deferred validation runs at entry; must not raise


def test_validation_failed_error_str_renders_inner_errors() -> None:
    # validate=False: exercise validate() directly rather than the construction-time raise.
    container = Container(groups=[CycleGroup], validate=False)
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    rendered = str(exc.value)
    assert "found 1 issue(s)" in rendered
    assert "Circular dependency detected" in rendered


def test_build_child_container_propagates_use_lock_false() -> None:
    root = Container(use_lock=False)
    root.open()
    child = root.build_child_container(scope=Scope.REQUEST)
    assert root._lock is None  # noqa: SLF001
    assert child._lock is None  # noqa: SLF001


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
    container = Container(scope=Scope.APP, validate=False)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        assert container.resolve(Container) is container
    assert container.closed is False  # self-healed: reopened by the warning path


def test_reenter_reopens_closed_container() -> None:
    container = Container(scope=Scope.APP, validate=False)
    container.close_sync()
    with container:  # __enter__ -> open() clears closed
        assert container.resolve(Container) is container


async def test_closed_container_async_path_warns() -> None:
    container = Container(scope=Scope.APP, validate=False)
    await container.close_async()
    with pytest.warns(ContainerClosedWarning):
        assert container.resolve(Container) is container


class _PersistentBroker: ...


class _AppBrokerGroup(Group):
    broker = providers.Factory(
        scope=Scope.APP, creator=_PersistentBroker, cache=providers.CacheSettings(clear_cache=False)
    )


def test_resolving_through_closed_parent_via_open_child_warns() -> None:
    app = Container(scope=Scope.APP, groups=[_AppBrokerGroup], validate=False)
    app.open()
    child = app.build_child_container(scope=Scope.REQUEST)
    child.open()
    app.close_sync()
    with pytest.warns(ContainerClosedWarning):
        assert isinstance(child.resolve(_PersistentBroker), _PersistentBroker)


async def test_async_context_manager_reopens() -> None:
    container = Container(scope=Scope.APP, validate=False)
    async with container:
        pass
    with pytest.warns(ContainerClosedWarning):
        container.resolve(Container)
    async with container:
        assert container.resolve(Container) is container


def test_open_reopens_closed_container() -> None:
    container = Container(scope=Scope.APP, validate=False)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        container.resolve(Container)
    container.open()
    assert container.resolve(Container) is container
    assert container.build_child_container(scope=Scope.REQUEST).scope is Scope.REQUEST


def test_reuse_after_close_warns_and_reopens() -> None:
    container = Container(scope=Scope.APP, validate=False)
    container.open()
    container.close_sync()
    with pytest.warns(ContainerClosedWarning) as record:
        assert container.resolve(Container) is container
    assert container.closed is False
    assert record[0].message.container_scope is Scope.APP  # ty: ignore[unresolved-attribute]


def test_reuse_warning_points_at_caller_not_library() -> None:
    container = Container(scope=Scope.APP, validate=False)
    container.open()
    container.close_sync()
    with pytest.warns(ContainerClosedWarning) as record:
        container.resolve(Container)
    assert record[0].filename == __file__


def test_explicit_open_after_close_does_not_warn() -> None:
    container = Container(scope=Scope.APP, validate=False)
    container.open()
    container.close_sync()
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a deliberate reopen is silent
        container.open()
        assert container.resolve(Container) is container


def test_child_built_off_closed_parent_warns_only_when_the_parent_resolves() -> None:
    app = Container(scope=Scope.APP, groups=[_AppBrokerGroup], validate=False)
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
    package_dir = container_module._PACKAGE_DIR  # noqa: SLF001
    sibling = f"{package_dir.rstrip(os.sep)}_fastapi{os.sep}routing.py"
    namespace: dict[str, typing.Any] = {}
    exec(compile("def integration(fn):\n    return fn()\n", sibling, "exec"), namespace)  # noqa: S102
    assert namespace["integration"](container_module._caller_stacklevel) == 1  # noqa: SLF001


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


def test_open_resurfaces_errors_held_by_add_providers() -> None:
    # Regression pin: open() must not short-circuit on an already-open container. It is documented
    # as the fail-fast verb, so registering a broken provider after open() and calling open() again
    # to re-check must still surface the held completeness error, not silently return.
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Broken:
        missing: Missing

    container = Container(scope=Scope.APP)
    container.open()
    container.add_providers(providers.Factory(creator=Broken))  # monotone half clean; completeness deferred
    assert container.providers_registry.has_pending_errors() is True

    with pytest.raises(ValidationFailedError) as exc:
        container.open()
    [issue] = exc.value.errors
    assert isinstance(issue, ArgumentResolutionError)


# --- open() is optional: first use prepares the container --------------------------------------


def test_fresh_container_starts_unopened() -> None:
    # A just-constructed container is not open, but it is usable: the first resolve prepares it.
    container = Container(scope=Scope.APP, validate=False)
    assert container.closed is True


def test_fresh_container_resolves_without_open() -> None:
    container = Container(scope=Scope.APP, validate=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a never-opened container must not warn
        assert container.resolve(Container) is container
    assert container.closed is False  # first touch prepared it


def test_fresh_container_builds_child_and_child_resolves_without_open() -> None:
    app = Container(scope=Scope.APP, validate=False)
    child = app.build_child_container(scope=Scope.REQUEST)
    assert child.resolve(Container) is child
    assert app.closed is True  # parenting a child does not open the parent


def test_build_child_off_closed_parent_is_allowed() -> None:
    app = Container(scope=Scope.APP, validate=False)
    app.open()
    app.close_sync()
    child = app.build_child_container(scope=Scope.REQUEST)  # no raise: builds nothing, resolves nothing
    assert child.scope is Scope.REQUEST


def test_first_touch_raises_held_completeness_errors() -> None:
    container = Container(scope=Scope.APP, groups=[_DeferBrokenGroup])  # never opened
    with pytest.raises(ValidationFailedError):
        container.resolve(_DeferBrokenService)


def test_child_first_touch_raises_held_completeness_errors() -> None:
    # Validation state lives on the shared registry, so a child-only path cannot skip it.
    root = Container(scope=Scope.APP, groups=[_DeferBrokenGroup])
    child = root.build_child_container(scope=Scope.REQUEST)
    with pytest.raises(ValidationFailedError):
        child.resolve(_DeferBrokenService)


def test_construction_validates_root_once_and_open_or_resolve_do_not(monkeypatch: pytest.MonkeyPatch) -> None:
    # A clean graph validates eagerly at construction, not at open(): count `_eager_validate` calls.
    calls = {"n": 0}
    real = Container._eager_validate  # noqa: SLF001

    def counting(self: Container) -> None:
        calls["n"] += 1
        real(self)

    monkeypatch.setattr(Container, "_eager_validate", counting)
    container = Container(scope=Scope.APP, groups=[_DeferValidGroup])  # default validate=True
    assert calls["n"] == 1  # construction validated the root exactly once
    container.open()
    assert container.closed is False
    assert calls["n"] == 1  # open() found nothing left to do
    assert isinstance(container.resolve(_DeferValidService), _DeferValidService)
    assert calls["n"] == 1  # resolve no longer validates


def test_child_from_build_requires_open_and_does_not_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    with Container(scope=Scope.APP, validate=False) as app:
        child = app.build_child_container(scope=Scope.REQUEST)
        assert child.closed is True  # child starts unopened too

        calls = {"n": 0}
        real = Container.validate

        def counting(self: Container) -> None:  # pragma: no cover -- asserted not to run
            calls["n"] += 1
            real(self)

        monkeypatch.setattr(Container, "validate", counting)
        child.open()  # child never validates (root-only)
        assert calls["n"] == 0
        assert child.resolve(Container) is child


def test_private_lock_and_scope_map_back_the_machinery() -> None:
    root = Container(use_lock=True)
    root.open()
    child = root.build_child_container(scope=Scope.REQUEST)

    # _lock is a reentrant lock (threading.RLock is a factory, not a type, so
    # assert behavior, not isinstance)
    assert root._lock is not None  # noqa: SLF001
    assert root._lock.acquire()  # noqa: SLF001
    assert root._lock.acquire()  # reentrant  # noqa: SLF001
    root._lock.release()  # noqa: SLF001
    root._lock.release()  # noqa: SLF001
    # child inherits the parent's scope map plus its own scope
    assert set(child._scope_map) == {Scope.APP, Scope.REQUEST}  # noqa: SLF001
    assert child._scope_map[Scope.APP] is root  # noqa: SLF001


def test_use_lock_false_yields_no_private_lock() -> None:
    root = Container(use_lock=False)
    root.open()
    child = root.build_child_container(scope=Scope.REQUEST)
    assert root._lock is None  # noqa: SLF001
    assert child._lock is None  # noqa: SLF001


def test_scope_map_alias_warns_and_forwards() -> None:
    container = Container()
    with pytest.warns(DeprecationWarning, match="scope_map"):
        aliased = container.scope_map
    assert aliased is container._scope_map  # noqa: SLF001


def test_lock_alias_warns_and_forwards() -> None:
    container = Container(use_lock=True)
    with pytest.warns(DeprecationWarning, match="lock"):
        aliased = container.lock
    assert aliased is container._lock  # noqa: SLF001


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


def test_default_and_true_both_enable_validation() -> None:
    # The default (None) and validate=True are identical — both enable validation, and a cycle
    # (monotone) raises at construction either way.
    with pytest.raises(ValidationFailedError):
        Container(scope=Scope.APP, groups=[CycleGroup])
    with pytest.raises(ValidationFailedError):
        Container(scope=Scope.APP, groups=[CycleGroup], validate=True)


def test_root_without_validate_arg_does_not_warn() -> None:
    # 3.0 removed UnvalidatedContainerWarning: constructing a root with unset validate is silent.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        Container(scope=Scope.APP)


def test_explicit_validate_false_never_warns() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        Container(scope=Scope.APP, validate=False)


def test_valid_graph_validates_clean_at_entry_without_warning() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Dep:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class ValidService:
        dep: Dep

    class ValidGroup(Group):
        dep = providers.Factory(creator=Dep)
        svc = providers.Factory(creator=ValidService)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with Container(scope=Scope.APP, groups=[ValidGroup], validate=True):  # validates clean at entry
            pass


def test_resolve_on_unopened_container_validates_then_raises() -> None:
    # resolve on a never-opened container prepares it first, which completes the held validation.
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        missing: Missing

    class G(Group):
        svc = providers.Factory(creator=Service)

    container = Container(scope=Scope.APP, groups=[G])  # constructs fine; broken graph not yet checked
    with pytest.raises(ValidationFailedError):
        container.resolve(Service)  # unopened -> prepares, which raises the held completeness error


def test_child_container_never_validates() -> None:
    # Root-only: only a root gets _validate_enabled; a child never validates regardless of the root's setting.
    root = Container(scope=Scope.APP, validate=True)
    assert root._validate_enabled is True  # noqa: SLF001
    root.open()
    child = root.build_child_container(scope=Scope.REQUEST)
    assert child._validate_enabled is False  # noqa: SLF001


def test_add_providers_registers_and_resolves_by_type_and_reference() -> None:
    container = Container(scope=Scope.APP, validate=False)
    container.open()
    str_factory = providers.Factory(creator=lambda: "added", bound_type=str)

    container.add_providers(str_factory)

    assert container.resolve(str) == "added"
    assert container.resolve_provider(str_factory) == "added"


def test_add_providers_raises_on_duplicate_against_registered() -> None:
    str_factory = providers.Factory(creator=lambda: "one", bound_type=str)
    other_str_factory = providers.Factory(creator=lambda: "two", bound_type=str)
    container = Container(scope=Scope.APP, validate=False)
    container.add_providers(str_factory)

    with pytest.raises(DuplicateProviderTypeError) as exc:
        container.add_providers(other_str_factory)
    assert exc.value.provider_type is str


def test_add_providers_raises_on_duplicate_intra_batch() -> None:
    str_factory = providers.Factory(creator=lambda: "one", bound_type=str)
    other_str_factory = providers.Factory(creator=lambda: "two", bound_type=str)
    container = Container(scope=Scope.APP, validate=False)

    with pytest.raises(DuplicateProviderTypeError) as exc:
        container.add_providers(str_factory, other_str_factory)
    assert exc.value.provider_type is str


def test_add_providers_on_child_container_raises() -> None:
    root = Container(scope=Scope.APP, validate=False)
    root.open()
    child = root.build_child_container(scope=Scope.REQUEST)
    str_factory = providers.Factory(creator=lambda: "added", bound_type=str)

    with pytest.raises(ChildContainerRegistrationError, match="root") as exc:
        child.add_providers(str_factory)
    assert isinstance(exc.value, exceptions.RegistrationError)
    assert exc.value.scope is Scope.REQUEST


def test_add_providers_defers_completeness_errors_to_first_use() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Broken:
        missing: Missing

    container = Container(scope=Scope.APP)
    container.validate()  # already validated at construction (clean, no groups) -- confirms the flag is set
    broken_factory = providers.Factory(creator=Broken)

    container.add_providers(broken_factory)  # monotone half is clean; completeness is deferred to first use

    with pytest.raises(ValidationFailedError) as exc:
        container.open()
    [issue] = exc.value.errors
    assert isinstance(issue, ArgumentResolutionError)


def test_add_providers_on_validate_false_root_does_not_validate() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Broken:
        missing: Missing

    container = Container(scope=Scope.APP, validate=False)
    broken_factory = providers.Factory(creator=Broken)

    container.add_providers(broken_factory)  # should not raise


def test_add_providers_on_unset_validate_root_does_not_validate() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Broken:
        missing: Missing

    # Unset validate walks eagerly at construction, but this graph's only error is completeness (a
    # missing dependency), which is deferred to first use: add_providers doesn't re-raise it, and a
    # later open() validates the completed graph. This is the integration seam.
    container = Container(scope=Scope.APP)
    broken_factory = providers.Factory(creator=Broken)

    container.add_providers(broken_factory)  # should not raise: not yet validated


def test_add_providers_rolls_back_whole_batch_when_revalidation_fails() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Original:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Inner:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Outer:
        inner: Inner

    class G(Group):
        original = providers.Factory(creator=Original)

    container = Container(scope=Scope.APP, groups=[G])
    container.open()

    valid_factory = providers.Factory(creator=lambda: "ok", bound_type=str)
    inner_factory = providers.Factory(scope=Scope.REQUEST, creator=Inner)
    outer_factory = providers.Factory(scope=Scope.APP, creator=Outer)  # scope-invalid: APP depends on REQUEST

    with pytest.raises(ValidationFailedError):
        container.add_providers(valid_factory, inner_factory, outer_factory)

    # the whole batch rolled back, including the valid providers
    with pytest.raises(ProviderNotRegisteredError):
        container.resolve(str)
    with pytest.raises(ProviderNotRegisteredError):
        container.resolve(Inner)
    with pytest.raises(ProviderNotRegisteredError):
        container.resolve(Outer)
    # the container is unchanged: original providers still resolve and the graph is still valid
    assert isinstance(container.resolve(Original), Original)
    container.validate()


def test_add_providers_defers_completeness_to_first_use_after_manual_validate() -> None:
    # This is what pins the `recheck` ordering in `add_providers`: reading the flag after the
    # registry mutation would silently skip re-validation on this manually-validated root.
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Broken:
        missing: Missing

    container = Container(scope=Scope.APP, validate=False)
    container.validate()  # manual call also sets the registry's validated flag
    broken_factory = providers.Factory(creator=Broken)

    container.add_providers(broken_factory)  # monotone half is clean; completeness is deferred to first use
    assert container.providers_registry.has_pending_errors() is True

    # Ruled: held errors surface at first use regardless of the enabled bit -- the manual validate()
    # call above is what arms the deferred check, so open() must still catch it on a validate=False root.
    with pytest.raises(ValidationFailedError) as exc:
        container.open()
    [issue] = exc.value.errors
    assert isinstance(issue, ArgumentResolutionError)


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

    container = Container(scope=Scope.APP, validate=True)
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

    container = Container(scope=Scope.APP, validate=False)
    container.open()
    outer_factory = providers.Factory(creator=Outer)

    with pytest.raises(ArgumentResolutionError):
        container.resolve_provider(outer_factory)

    container.add_providers(providers.Factory(creator=Inner))

    result = container.resolve_provider(outer_factory)
    assert isinstance(result.inner, Inner)


def test_add_providers_rolls_back_on_any_exception_from_revalidation() -> None:
    """Rollback must not be tied to ValidationFailedError specifically — any exception rolls back."""
    container = Container(scope=Scope.APP)  # clean graph -> already validated at construction
    str_factory = providers.Factory(creator=lambda: "added", bound_type=str)

    def _boom(_self: Container) -> None:
        msg = "boom"
        raise RuntimeError(msg)

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(Container, "_eager_validate", _boom)
        with pytest.raises(RuntimeError, match="boom"):
            container.add_providers(str_factory)

    with pytest.raises(ProviderNotRegisteredError):
        container.resolve(str)


def test_add_providers_on_validated_root_with_valid_batch_succeeds() -> None:
    """Positive branch: a validated root re-validates successfully and the batch resolves afterwards."""
    container = Container(scope=Scope.APP)
    container.open()
    container.validate()  # deferred: validate first so add_providers exercises the success re-validation branch
    str_factory = providers.Factory(creator=lambda: "added", bound_type=str)

    container.add_providers(str_factory)

    assert container.resolve(str) == "added"


def test_add_providers_on_closed_root_registers_fine() -> None:
    """Ruled: no closed-state check on add_providers — registering on a closed root just works."""
    container = Container(scope=Scope.APP, validate=False)
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
    container = Container(groups=[_OverrideGroup], validate=False)
    container.open()
    mock = _OverrideSvc()
    with container.override(_OverrideGroup.svc, mock) as bound:
        assert bound is mock
        assert container.resolve(_OverrideSvc) is mock
    assert container.resolve(_OverrideSvc) is not mock


def test_override_context_manager_restores_prior_imperative_override() -> None:
    container = Container(groups=[_OverrideGroup], validate=False)
    container.open()
    first = _OverrideSvc()
    second = _OverrideSvc()
    container.override(_OverrideGroup.svc, first)
    with container.override(_OverrideGroup.svc, second):
        assert container.resolve(_OverrideSvc) is second
    assert container.resolve(_OverrideSvc) is first


def test_override_context_manager_nested_unwinds_in_order() -> None:
    container = Container(groups=[_OverrideGroup], validate=False)
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
    container = Container(groups=[_OverrideGroup], validate=False)
    container.open()
    mock = _OverrideSvc()
    msg = "boom"
    with pytest.raises(RuntimeError), container.override(_OverrideGroup.svc, mock):
        raise RuntimeError(msg)
    assert container.resolve(_OverrideSvc) is not mock


def test_override_context_manager_exit_restores_snapshot_after_inner_reset() -> None:
    container = Container(groups=[_OverrideGroup], validate=False)
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
    container = Container(validate=False)
    container.open()
    with pytest.raises(TypeError, match="no compiled resolver for provider type _UnknownProvider"):
        container.resolve_provider(provider)


# --- Deferred validate-by-default (3.0 both-deferred) ---------------------------------------------


@dataclasses.dataclass(kw_only=True, slots=True)
class _DeferMissing:
    pass


@dataclasses.dataclass(kw_only=True, slots=True)
class _DeferBrokenService:
    missing: _DeferMissing  # no provider registered for _DeferMissing -> validation fails


class _DeferBrokenGroup(Group):
    svc = providers.Factory(creator=_DeferBrokenService)


@dataclasses.dataclass(kw_only=True, slots=True)
class _DeferValidService:
    pass


class _DeferValidGroup(Group):
    svc = providers.Factory(creator=_DeferValidService)


class _DeferRequest: ...


@dataclasses.dataclass(kw_only=True, slots=True)
class _DeferReqDependent:
    request: _DeferRequest


class _DeferFactoryNeedingRequestGroup(Group):
    # Depends by-type on _DeferRequest, whose ContextProvider an integration registers after construction.
    dependent = providers.Factory(creator=_DeferReqDependent)


def test_invalid_graph_does_not_raise_at_construction() -> None:
    container = Container(scope=Scope.APP, groups=[_DeferBrokenGroup])  # no raise: validation is deferred
    with pytest.raises(ValidationFailedError):
        container.open()  # validation runs at container entry


def test_validation_completes_at_first_touch() -> None:
    # First use prepares the container, which completes the held validation and surfaces it.
    container = Container(scope=Scope.APP, groups=[_DeferBrokenGroup])
    with pytest.raises(ValidationFailedError):
        container.resolve(_DeferBrokenService)


def test_deferred_validation_raises_via_context_manager_entry() -> None:
    container = Container(scope=Scope.APP, groups=[_DeferBrokenGroup])
    with pytest.raises(ValidationFailedError), container:
        pass  # pragma: no cover -- __enter__ raises before the body runs


def test_reopen_does_not_revalidate(monkeypatch: pytest.MonkeyPatch) -> None:
    # A clean graph validates eagerly at construction, not at open(): count `_eager_validate` calls.
    calls = {"n": 0}
    real = Container._eager_validate  # noqa: SLF001

    def counting(self: Container) -> None:
        calls["n"] += 1
        real(self)

    monkeypatch.setattr(Container, "_eager_validate", counting)
    container = Container(scope=Scope.APP, groups=[_DeferValidGroup])
    with container:
        container.resolve(_DeferValidService)
    with container:  # reopen must not re-walk the graph
        container.resolve(_DeferValidService)
    assert calls["n"] == 1  # validated once, at construction; open/reopen/resolve never re-walk


def test_validate_false_never_validates() -> None:
    container = Container(scope=Scope.APP, groups=[_DeferBrokenGroup], validate=False)
    with container:  # validation is off -> the broken graph is never checked
        pass


def test_integration_pattern_context_registered_after_construction() -> None:
    # The root-cause scenario: an integration registers its ContextProvider AFTER the user constructs the
    # container. With deferred validation the graph is complete before validation runs, so no false failure.
    container = Container(scope=Scope.APP, groups=[_DeferFactoryNeedingRequestGroup])  # no raise
    container.add_providers(providers.ContextProvider(_DeferRequest))  # integration wires it in
    with container:  # graph now complete -> validates clean
        pass


def test_missing_dependency_does_not_raise_at_construction() -> None:
    # Non-monotone: an integration may still register the missing provider via add_providers.
    container = Container(scope=Scope.APP, groups=[_DeferBrokenGroup])
    assert container.providers_registry.has_pending_errors() is True
    with pytest.raises(ValidationFailedError):
        container.open()


def test_clean_graph_is_marked_validated_at_construction() -> None:
    container = Container(scope=Scope.APP, groups=[_DeferValidGroup])
    assert container.providers_registry.is_validated() is True
    assert container.providers_registry.has_pending_errors() is False


def test_validate_false_walks_nothing_at_construction() -> None:
    container = Container(scope=Scope.APP, groups=[CycleGroup], validate=False)  # no raise
    assert container.providers_registry.is_validated() is False
    assert container.providers_registry.has_pending_errors() is False


def test_add_providers_completes_a_pending_graph() -> None:
    # The integration seam: a by-type dependency on a provider registered after construction.
    container = Container(scope=Scope.APP, groups=[_DeferFactoryNeedingRequestGroup])
    assert container.providers_registry.has_pending_errors() is True
    container.add_providers(providers.ContextProvider(_DeferRequest))  # integration wires it in
    # `add_providers` re-walks itself, so the graph is already clean here — no `open()` needed.
    assert container.providers_registry.is_validated() is True
    assert container.providers_registry.has_pending_errors() is False


def test_add_providers_completed_graph_resolves_without_an_explicit_open() -> None:
    # Same seam, reached the way an unopened container reaches it: the first resolve prepares.
    container = Container(
        scope=Scope.APP,
        groups=[_DeferFactoryNeedingRequestGroup],
        context={_DeferRequest: _DeferRequest()},
    )
    container.add_providers(providers.ContextProvider(_DeferRequest))  # integration wires it in
    request = container.build_child_container(scope=Scope.REQUEST)
    assert isinstance(request.resolve(_DeferReqDependent), _DeferReqDependent)  # no explicit open()
    assert container.closed is False


def test_open_revalidates_when_pending_cleared_by_direct_registry_mutation() -> None:
    # `take_pending_errors()` comes back empty for two reasons: the graph was clean at construction
    # (validate() then short-circuits on is_validated()), or a mutation cleared the pending list
    # without re-walking (validate() then re-walks the complete graph). This drives the second path,
    # via the registry's own `add_providers`, which bypasses `Container.add_providers`'s re-check.
    container = Container(scope=Scope.APP, groups=[_DeferFactoryNeedingRequestGroup])
    assert container.providers_registry.has_pending_errors() is True
    container.providers_registry.add_providers(providers.ContextProvider(_DeferRequest))
    assert container.providers_registry.has_pending_errors() is False  # invalidate() cleared it, unwalked
    container.open()  # _complete_validation finds no pending errors and falls through to validate()
    assert container.providers_registry.is_validated() is True
