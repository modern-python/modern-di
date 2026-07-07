import copy
import dataclasses
import pathlib
import re
import typing
import warnings

import pytest

from modern_di import Container, Group, Scope, exceptions, providers
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
    with pytest.raises(ScopeSkippedError, match=r"No APP-scope container exists in this chain") as exc:
        container.resolve_provider(app_factory)
    assert exc.value.provider_scope == Scope.APP


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


def test_validate_on_creation() -> None:
    with pytest.raises(ValidationFailedError) as exc:
        Container(groups=[CycleGroup], validate=True)
    [issue] = exc.value.errors
    assert isinstance(issue, CircularDependencyError)


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

    Container(groups=[G], validate=True)


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

    Container(groups=[G], validate=True)


def test_validation_failed_error_str_renders_inner_errors() -> None:
    container = Container(groups=[CycleGroup])
    with pytest.raises(ValidationFailedError) as exc:
        container.validate()
    rendered = str(exc.value)
    assert "found 1 issue(s)" in rendered
    assert "Circular dependency detected" in rendered


def test_build_child_container_propagates_use_lock_false() -> None:
    root = Container(use_lock=False)
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
    instance = container.resolve(Service)
    assert instance.di_container is container


def test_container_rejects_non_intenum_scope_at_init() -> None:
    with pytest.raises(InvalidScopeTypeError) as exc:
        Container(scope=99)  # ty: ignore[invalid-argument-type]
    assert "99" in str(exc.value)


def test_constructor_rejects_parent_with_non_increasing_scope() -> None:
    app = Container(scope=Scope.APP)
    with pytest.raises(InvalidChildScopeError):
        Container(scope=Scope.APP, parent_container=app)
    request = app.build_child_container(scope=Scope.REQUEST)
    with pytest.raises(InvalidChildScopeError):
        Container(scope=Scope.APP, parent_container=request)


def test_closed_container_warns_and_reopens_on_resolve_and_child_building() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        container.resolve(Container)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        container.build_child_container(scope=Scope.REQUEST)


async def test_closed_container_async_path() -> None:
    container = Container(scope=Scope.APP)
    await container.close_async()
    with pytest.warns(ContainerClosedWarning):
        assert container.resolve(Container) is container


class _PersistentBroker: ...


class _AppBrokerGroup(Group):
    broker = providers.Factory(
        scope=Scope.APP, creator=_PersistentBroker, cache=providers.CacheSettings(clear_cache=False)
    )


def test_resolving_through_closed_parent_via_open_child_warns_and_reopens() -> None:
    app = Container(scope=Scope.APP, groups=[_AppBrokerGroup])
    child = app.build_child_container(scope=Scope.REQUEST)
    app.close_sync()
    with pytest.warns(ContainerClosedWarning):
        broker = child.resolve(_PersistentBroker)
    assert isinstance(broker, _PersistentBroker)
    assert app.closed is False


async def test_async_context_manager_reopens() -> None:
    container = Container(scope=Scope.APP)
    async with container:
        pass
    with pytest.warns(ContainerClosedWarning):
        assert container.resolve(Container) is container
    async with container:
        assert container.resolve(Container) is container


def test_open_reopens_closed_container() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        assert container.resolve(Container) is container
    container.open()
    assert container.resolve(Container) is container
    assert container.build_child_container(scope=Scope.REQUEST).scope is Scope.REQUEST


def test_reuse_after_close_warns_and_reopens() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        resolved = container.resolve(Container)
    assert resolved is container
    assert container.closed is False


def test_build_child_after_close_warns_and_reopens() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with pytest.warns(ContainerClosedWarning):
        child = container.build_child_container(scope=Scope.REQUEST)
    assert container.closed is False
    assert child.scope is Scope.REQUEST


def test_reuse_warns_once_per_close_cycle() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        container.resolve(Container)
        container.resolve(Container)
    closed_warnings = [w for w in caught if issubclass(w.category, ContainerClosedWarning)]
    assert len(closed_warnings) == 1


def test_strict_opt_in_reuse_raises() -> None:
    container = Container(scope=Scope.APP)
    container.close_sync()
    with warnings.catch_warnings():
        warnings.simplefilter("error", ContainerClosedWarning)
        with pytest.raises(ContainerClosedWarning):
            container.resolve(Container)


def test_container_closed_error_message_and_attr() -> None:
    err = ContainerClosedError(container_scope=Scope.APP)
    assert err.container_scope is Scope.APP
    assert "closed" in str(err)
    assert "Create a new container" in str(err)


def test_open_on_open_container_is_noop() -> None:
    container = Container(scope=Scope.APP)
    container.open()
    assert container.closed is False
    assert container.resolve(Container) is container


def test_private_lock_and_scope_map_back_the_machinery() -> None:
    root = Container(use_lock=True)
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
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        container.resolve(_Dep)  # touches _lock and _scope_map internally
        container.build_child_container(scope=Scope.REQUEST)


def test_root_container_without_validate_arg_warns_about_3_0_default() -> None:
    with pytest.warns(exceptions.UnvalidatedContainerWarning, match="modern-di 3.0 runs validate"):
        Container(scope=Scope.APP)


def test_explicit_validate_false_never_warns() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        Container(scope=Scope.APP, validate=False)


def test_explicit_validate_true_validates_and_never_warns() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class BrokenService:
        missing: Missing

    class BrokenGroup(Group):
        svc = providers.Factory(creator=BrokenService)

    with pytest.raises(ValidationFailedError):
        Container(scope=Scope.APP, groups=[BrokenGroup], validate=True)

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
        Container(scope=Scope.APP, groups=[ValidGroup], validate=True)


def test_unset_validate_warns_but_does_not_validate() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Service:
        missing: Missing

    class G(Group):
        svc = providers.Factory(creator=Service)

    with pytest.warns(exceptions.UnvalidatedContainerWarning):
        Container(scope=Scope.APP, groups=[G])  # constructs fine; the broken graph is never checked

    with pytest.raises(ValidationFailedError):
        Container(scope=Scope.APP, groups=[G], validate=True)


def test_child_container_does_not_warn_about_validate() -> None:
    root = Container(scope=Scope.APP, validate=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        root.build_child_container(scope=Scope.REQUEST)


def test_unvalidated_container_warning_is_escalatable() -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=exceptions.UnvalidatedContainerWarning)
        with pytest.raises(exceptions.UnvalidatedContainerWarning):
            Container(scope=Scope.APP)


def test_unvalidated_warning_pyproject_filter_matches_live_message() -> None:
    """The pyproject.toml filterwarnings message must keep matching the live warning text.

    The filter is message-based on purpose (see the comment in pyproject.toml), so nothing
    else ties it to the warning it silences. If the wording in container.py drifts, this test
    catches it instead of the suite silently filling with warning noise.
    """
    with pytest.warns(exceptions.UnvalidatedContainerWarning) as record:
        Container(scope=Scope.APP)

    pyproject_path = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    raw = pyproject_path.read_text()
    pattern = re.search(r'"ignore:(?P<message>[^"]+):FutureWarning"', raw)
    assert pattern is not None, "no ignore:...:FutureWarning filter found in pyproject.toml filterwarnings"

    assert re.compile(pattern.group("message")).match(str(record[0].message)) is not None


def test_add_providers_registers_and_resolves_by_type_and_reference() -> None:
    container = Container(scope=Scope.APP, validate=False)
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
    child = root.build_child_container(scope=Scope.REQUEST)
    str_factory = providers.Factory(creator=lambda: "added", bound_type=str)

    with pytest.raises(ChildContainerRegistrationError, match="root") as exc:
        child.add_providers(str_factory)
    assert isinstance(exc.value, exceptions.RegistrationError)


def test_add_providers_on_validated_root_reraises_validation_failure() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Broken:
        missing: Missing

    container = Container(scope=Scope.APP, validate=True)
    broken_factory = providers.Factory(creator=Broken)

    with pytest.raises(ValidationFailedError) as exc:
        container.add_providers(broken_factory)
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

    with pytest.warns(exceptions.UnvalidatedContainerWarning):
        container = Container(scope=Scope.APP)
    broken_factory = providers.Factory(creator=Broken)

    container.add_providers(broken_factory)  # should not raise


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

    container = Container(scope=Scope.APP, groups=[G], validate=True)

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


def test_add_providers_after_manual_validate_reraises_validation_failure() -> None:
    @dataclasses.dataclass(kw_only=True, slots=True)
    class Missing:
        pass

    @dataclasses.dataclass(kw_only=True, slots=True)
    class Broken:
        missing: Missing

    container = Container(scope=Scope.APP, validate=False)
    container.validate()  # manual call also sets the flag
    broken_factory = providers.Factory(creator=Broken)

    with pytest.raises(ValidationFailedError) as exc:
        container.add_providers(broken_factory)
    [issue] = exc.value.errors
    assert isinstance(issue, ArgumentResolutionError)
