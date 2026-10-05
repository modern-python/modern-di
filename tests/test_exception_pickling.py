"""Every modern-di exception survives pickle, copy and deepcopy with its type and message intact."""

import copy
import enum
import functools
import pickle
import threading
import typing

import pytest

from modern_di import Container, Scope, exceptions, providers, suggester


class Tenancy(enum.IntEnum):
    TENANT = 2


class Database:
    pass


class Repository:
    pass


def make_repository(database: Database) -> Repository:
    raise NotImplementedError  # pragma: no cover - named in errors, never called


class KeywordOnlyError(Exception):
    def __init__(self, *, detail: str) -> None:
        super().__init__(f"detail={detail}")


_app_provider = providers.Factory(scope=Scope.APP, creator=make_repository)
_request_provider = providers.Factory(scope=Scope.REQUEST, creator=Database)
_tenant_provider = providers.Factory(scope=Tenancy.TENANT, creator=Database)


def _step(name: str, scope: enum.IntEnum = Scope.APP) -> exceptions.ResolutionStep:
    return exceptions.ResolutionStep(scope=scope, name=name, location=f"app:{len(name)}")


def _with_path(error: exceptions.ResolutionError) -> exceptions.ResolutionError:
    error.prepend_step(_step("Service"), _step("Repository", Scope.REQUEST))
    return error


def _with_cause(error: BaseException, cause: BaseException) -> BaseException:
    error.__cause__ = cause
    return error


def _closed_container_error() -> exceptions.ContainerClosedError:
    container = Container()
    container.close_sync()
    with pytest.raises(exceptions.ContainerClosedError) as info:
        container.resolve(int)
    return info.value


def _context_error() -> exceptions.ContextValueNotSetError:
    error = exceptions.ContextValueNotSetError(context_type=Database, provider_scope=Scope.REQUEST)
    error.name_parameter("database")
    return error


_SUGGESTIONS = [suggester.Suggestion(name="Database", reason="similar name", scope=Scope.APP)]

BUILDERS: dict[type[exceptions.ModernDIError], typing.Callable[[], BaseException]] = {
    exceptions.ModernDIError: lambda: exceptions.ModernDIError("boom"),
    exceptions.ContainerError: lambda: exceptions.ContainerError("boom"),
    exceptions.ResolutionError: lambda: _with_path(exceptions.ResolutionError("boom")),
    exceptions.RegistrationError: lambda: exceptions.RegistrationError("boom"),
    exceptions.InvalidChildScopeError: lambda: exceptions.InvalidChildScopeError(
        parent_scope=Scope.REQUEST, child_scope=Scope.APP
    ),
    exceptions.MaxScopeReachedError: lambda: exceptions.MaxScopeReachedError(parent_scope=Scope.STEP),
    exceptions.ScopeNotInitializedError: lambda: _with_path(
        exceptions.ScopeNotInitializedError(provider_scope=Scope.REQUEST, container_scope=Scope.APP)
    ),
    exceptions.ScopeSkippedError: lambda: exceptions.ScopeSkippedError(
        provider_scope=Scope.APP, container_scope=Scope.REQUEST
    ),
    exceptions.InvalidScopeTypeError: lambda: exceptions.InvalidScopeTypeError(scope_value="app"),
    exceptions.ContainerClosedError: _closed_container_error,
    exceptions.ValidationFailedError: lambda: exceptions.ValidationFailedError(
        errors=[
            exceptions.ProviderNotRegisteredError(provider_type=Database, suggestions=_SUGGESTIONS),
            exceptions.CircularDependencyError(steps=[_step("A"), _step("B"), _step("A")]),
        ]
    ),
    exceptions.FinalizerError: lambda: exceptions.FinalizerError(
        finalizer_errors=[
            ValueError("close failed"),
            exceptions.AsyncFinalizerInSyncCloseError(finalizer_type=Database),
        ],
        is_async=False,
    ),
    exceptions.AsyncFinalizerInSyncCloseError: lambda: exceptions.AsyncFinalizerInSyncCloseError(
        finalizer_type=Database
    ),
    exceptions.GroupInstantiationError: lambda: exceptions.GroupInstantiationError(group_name="Dependencies"),
    exceptions.DuplicateProviderTypeError: lambda: exceptions.DuplicateProviderTypeError(provider_type=Database),
    exceptions.ChildContainerRegistrationError: lambda: exceptions.ChildContainerRegistrationError(scope=Scope.REQUEST),
    exceptions.ProviderScopeFrozenError: lambda: exceptions.ProviderScopeFrozenError(
        provider_name="database", group_name="Dependencies", current_scope=Scope.APP, new_scope=Scope.REQUEST
    ),
    exceptions.GroupScopeConflictError: lambda: exceptions.GroupScopeConflictError(
        provider_name="database",
        first_group="First",
        first_scope=Scope.APP,
        second_group="Second",
        second_scope=Scope.REQUEST,
    ),
    exceptions.UnknownFactoryKwargError: lambda: exceptions.UnknownFactoryKwargError(
        creator=make_repository, unknown_keys=["databse"], known_keys=["database"]
    ),
    exceptions.UnsupportedCreatorParameterError: lambda: exceptions.UnsupportedCreatorParameterError(
        creator=make_repository, parameter_name="args", reason="variadic parameters are not supported"
    ),
    exceptions.InvalidScopeDependencyError: lambda: exceptions.InvalidScopeDependencyError(
        provider=_app_provider, parameter_name="database", dep_chain=[_request_provider]
    ),
    exceptions.ScopeEnumMismatchError: lambda: exceptions.ScopeEnumMismatchError(
        provider=_app_provider, parameter_name="database", dep_chain=[_tenant_provider]
    ),
    exceptions.ProviderNotRegisteredError: lambda: _with_path(
        exceptions.ProviderNotRegisteredError(provider_type=Database, suggestions=_SUGGESTIONS)
    ),
    exceptions.AliasSourceNotRegisteredError: lambda: exceptions.AliasSourceNotRegisteredError(source_type=Database),
    exceptions.ArgumentResolutionError: lambda: exceptions.ArgumentResolutionError(
        parameter_name="database",
        parameter_type=None,
        bound_type=Repository,
        creator=make_repository,
        suggestions=_SUGGESTIONS,
        member_types=[Database, Repository],
    ),
    exceptions.CreatorCallError: lambda: _with_cause(
        _with_path(exceptions.CreatorCallError(creator=make_repository, original_error=TypeError("bad kwarg"))),
        TypeError("bad kwarg"),
    ),
    exceptions.CircularDependencyError: lambda: _with_cause(
        exceptions.CircularDependencyError(steps=[_step("A"), _step("B", Scope.REQUEST), _step("A")]),
        RecursionError("too deep"),
    ),
    exceptions.ContextValueNotSetError: _context_error,
}


def _all_subclasses(cls: type) -> set[type]:
    return {cls}.union(*(_all_subclasses(sub) for sub in cls.__subclasses__()))


def _public_state(error: BaseException) -> dict[str, typing.Any]:
    names = {
        name for klass in type(error).__mro__ for name in vars(klass).get("__slots__", ()) if not name.startswith("_")
    }
    state = {name: getattr(error, name) for name in names}
    state.update({name: value for name, value in vars(error).items() if not name.startswith("_")})
    return state


def _comparable(value: object) -> object:
    if isinstance(value, BaseException):
        return type(value), str(value)
    if isinstance(value, list | tuple):
        return [_comparable(item) for item in value]
    return repr(value)


def _pickle_round_trip(error: BaseException, protocol: int) -> BaseException:
    return pickle.loads(pickle.dumps(error, protocol=protocol))  # noqa: S301


_PROTOCOLS = range(pickle.HIGHEST_PROTOCOL + 1)
ROUND_TRIPS: dict[str, typing.Callable[[BaseException], BaseException]] = {
    **{f"pickle-{protocol}": functools.partial(_pickle_round_trip, protocol=protocol) for protocol in _PROTOCOLS},
    "copy": copy.copy,
    "deepcopy": copy.deepcopy,
}


def _within(seconds: float, call: typing.Callable[[], BaseException]) -> BaseException:
    result: list[BaseException] = []
    worker = threading.Thread(target=lambda: result.append(call()), daemon=True)
    worker.start()
    worker.join(seconds)
    assert not worker.is_alive(), f"did not finish within {seconds}s"
    return result[0]


def test_every_modern_di_exception_has_a_builder() -> None:
    discovered = {cls for cls in _all_subclasses(exceptions.ModernDIError) if cls.__module__.startswith("modern_di.")}
    exported = {obj for obj in vars(exceptions).values() if isinstance(obj, type) and issubclass(obj, BaseException)}
    assert discovered <= exported
    assert set(BUILDERS) == discovered


_SLOTTED_PROVIDERS_DEGRADE = {"pickle-0", "pickle-1"}


def _degrade_providers(state: dict[str, typing.Any]) -> dict[str, typing.Any]:
    return {name: repr(value) if name in {"provider", "dep_chain"} else value for name, value in state.items()}


@pytest.mark.parametrize("trip_name", ROUND_TRIPS)
@pytest.mark.parametrize("cls", BUILDERS, ids=lambda cls: cls.__name__)
def test_exception_round_trips(cls: type[exceptions.ModernDIError], trip_name: str) -> None:
    error = BUILDERS[cls]()
    error.add_note("raised in a worker")
    assert type(error) is cls

    restored = ROUND_TRIPS[trip_name](error)

    expected_state = _public_state(error)
    if trip_name in _SLOTTED_PROVIDERS_DEGRADE:
        expected_state = _degrade_providers(expected_state)

    assert type(restored) is cls
    assert str(restored) == str(error)
    assert _comparable(restored.args) == _comparable(error.args)
    assert restored.__notes__ == ["raised in a worker"]
    assert _comparable(_public_state(restored)) == _comparable(expected_state)


def test_dependency_path_survives_pickling() -> None:
    error = BUILDERS[exceptions.ProviderNotRegisteredError]()
    assert isinstance(error, exceptions.ProviderNotRegisteredError)
    restored = pickle.loads(pickle.dumps(error))  # noqa: S301
    assert isinstance(restored, exceptions.ProviderNotRegisteredError)
    assert restored.dependency_path == error.dependency_path
    assert restored.suggestions == error.suggestions


def test_pickling_drops_the_cause_like_any_python_exception() -> None:
    error = BUILDERS[exceptions.CircularDependencyError]()
    assert isinstance(error.__cause__, RecursionError)
    assert pickle.loads(pickle.dumps(error)).__cause__ is None  # noqa: S301


def test_unpickled_finalizer_error_still_splits() -> None:
    error = BUILDERS[exceptions.FinalizerError]()
    restored = pickle.loads(pickle.dumps(error))  # noqa: S301
    matched, rest = restored.split(exceptions.AsyncFinalizerInSyncCloseError)
    assert isinstance(matched, exceptions.FinalizerError)
    assert isinstance(rest, exceptions.FinalizerError)
    assert matched.is_async is False
    assert [type(e) for e in rest.exceptions] == [ValueError]


def _local_creator_error() -> exceptions.ModernDIError:
    return exceptions.UnsupportedCreatorParameterError(
        creator=lambda: None, parameter_name="args", reason="variadic parameters are not supported"
    )


def _local_type_error() -> exceptions.ModernDIError:
    class LocalService:
        pass

    return exceptions.ProviderNotRegisteredError(provider_type=LocalService)


def _local_scope_error() -> exceptions.ModernDIError:
    class LocalScope(enum.IntEnum):
        JOB = 7

    error = exceptions.ScopeNotInitializedError(provider_scope=LocalScope.JOB, container_scope=Scope.APP)
    error.prepend_step(_step("Job", LocalScope.JOB))
    return error


def _local_provider_error() -> exceptions.ModernDIError:
    provider = providers.Factory(scope=Scope.APP, creator=lambda database: Repository())  # noqa: ARG005
    return exceptions.InvalidScopeDependencyError(
        provider=provider, parameter_name="database", dep_chain=[_request_provider]
    )


@pytest.mark.parametrize(
    ("build", "attribute"),
    [
        (_local_creator_error, "creator"),
        (_local_type_error, "provider_type"),
        (_local_scope_error, "provider_scope"),
        (_local_scope_error, "dependency_path"),
        (_local_provider_error, "provider"),
    ],
)
def test_unpicklable_attribute_degrades_to_its_repr(
    build: typing.Callable[[], exceptions.ModernDIError], attribute: str
) -> None:
    error = build()

    restored = pickle.loads(pickle.dumps(error))  # noqa: S301

    assert type(restored) is type(error)
    assert str(restored) == str(error)
    assert getattr(restored, attribute) == repr(getattr(error, attribute))


def test_unpicklable_finalizer_error_becomes_a_placeholder_exception() -> None:
    original = KeywordOnlyError(detail="disk full")
    error = exceptions.FinalizerError(finalizer_errors=[original, ValueError("other")], is_async=True)

    restored = pickle.loads(pickle.dumps(error))  # noqa: S301

    assert str(restored) == str(error)
    assert restored.is_async is True
    placeholder, kept = restored.exceptions
    assert type(placeholder) is RuntimeError
    assert str(placeholder) == repr(original)
    assert type(kept) is ValueError


@pytest.mark.parametrize("copier", [copy.copy, copy.deepcopy])
def test_copies_keep_unpicklable_attributes(copier: typing.Callable[[BaseException], BaseException]) -> None:
    error = _local_creator_error()
    assert isinstance(error, exceptions.UnsupportedCreatorParameterError)

    copied = copier(error)

    assert isinstance(copied, exceptions.UnsupportedCreatorParameterError)
    assert copied.creator is error.creator
    assert str(copied) == str(error)


def test_attribute_with_a_broken_repr_degrades_to_the_default_repr() -> None:
    class BrokenRepr:
        def __str__(self) -> str:
            return "BrokenRepr"

        def __repr__(self) -> str:
            raise ValueError

    value = BrokenRepr()
    error = exceptions.DuplicateProviderTypeError(provider_type=typing.cast("type", value))

    restored = pickle.loads(pickle.dumps(error))  # noqa: S301

    assert str(restored) == str(error)
    assert isinstance(restored, exceptions.DuplicateProviderTypeError)
    assert restored.provider_type == object.__repr__(value)


def _self_referencing_error() -> exceptions.ContainerClosedError:
    error = exceptions.ContainerClosedError(container_scope=Scope.APP)
    error.backref = error  # ty: ignore[unresolved-attribute]
    return error


@pytest.mark.parametrize(
    "round_trip",
    [trip for name, trip in ROUND_TRIPS.items() if name != "copy"],
    ids=[name for name in ROUND_TRIPS if name != "copy"],
)
def test_self_reference_is_restored_as_a_self_reference(
    round_trip: typing.Callable[[BaseException], BaseException],
) -> None:
    error = _self_referencing_error()

    restored = _within(5, lambda: round_trip(error))

    assert restored.backref is restored  # ty: ignore[unresolved-attribute]


def test_shallow_copy_of_a_self_reference_points_at_the_original() -> None:
    error = _self_referencing_error()
    assert copy.copy(error).backref is error  # ty: ignore[unresolved-attribute]


@pytest.mark.parametrize("round_trip", ROUND_TRIPS.values(), ids=ROUND_TRIPS.keys())
def test_deeply_nested_errors_round_trip_quickly(round_trip: typing.Callable[[BaseException], BaseException]) -> None:
    depth = 40
    error: Exception = ValueError("root")
    for _ in range(depth):
        error = exceptions.CreatorCallError(creator=len, original_error=error)

    restored = _within(5, lambda: round_trip(error))

    for _ in range(depth):
        assert isinstance(restored, exceptions.CreatorCallError)
        restored = restored.original_error
    assert type(restored) is ValueError
