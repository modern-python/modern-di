import dataclasses

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import (
    DuplicateProviderTypeError,
    GroupInstantiationError,
    GroupScopeConflictError,
    InvalidScopeTypeError,
)


def test_group_cannot_be_instantiated() -> None:
    class Dependencies(Group): ...

    with pytest.raises(GroupInstantiationError, match="Dependencies cannot be instantiated") as exc:
        Dependencies()
    assert exc.value.group_name == "Dependencies"


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class _A:
    pass


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class _B:
    pass


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class _C:
    pass


def test_group_inherits_providers_from_parent() -> None:
    class Base(Group):
        a = providers.Factory(creator=_A)

    class Child(Base):
        b = providers.Factory(creator=_B)

    container = Container(groups=[Child])
    container.open()
    assert isinstance(container.resolve(_A), _A)
    assert isinstance(container.resolve(_B), _B)


def test_group_subclass_overrides_parent_provider() -> None:
    class Base(Group):
        a = providers.Factory(creator=_A)

    class Child(Base):
        a = providers.Factory(creator=_A, bound_type=_B)  # override; resolve _B yields _A instance

    container = Container(groups=[Child])
    container.open()
    assert isinstance(container.resolve(_B), _A)


def test_group_non_provider_override_masks_parent_provider() -> None:
    class Base(Group):
        a = providers.Factory(creator=_A)

    class Child(Base):
        a = "not a provider"

    assert Child.get_providers() == []


def test_group_diamond_inheritance_returns_each_provider_once() -> None:
    class Base(Group):
        a = providers.Factory(creator=_A)

    class Left(Base): ...

    class Right(Base): ...

    class Diamond(Left, Right): ...

    providers_list = Diamond.get_providers()
    assert len(providers_list) == 1
    assert providers_list[0] is Base.a


class _DupA: ...


class _ExtraSvc: ...


class _GroupOne(Group):
    a = providers.Factory(scope=Scope.APP, creator=_DupA)


class _GroupTwo(Group):
    extra = providers.Factory(scope=Scope.APP, creator=_ExtraSvc)
    a_again = providers.Factory(scope=Scope.APP, creator=_DupA)


def test_duplicate_type_across_two_groups_raises() -> None:
    with pytest.raises(DuplicateProviderTypeError):
        Container(scope=Scope.APP, groups=[_GroupOne, _GroupTwo])


def test_failed_group_registration_does_not_pollute_shared_registry() -> None:
    app = Container(scope=Scope.APP, groups=[_GroupOne])
    child_scope = Scope.SESSION
    with pytest.raises(DuplicateProviderTypeError):
        Container(scope=child_scope, parent_container=app, groups=[_GroupTwo])
    assert app.providers_registry.find_provider(_ExtraSvc) is None


def test_get_named_providers_maps_each_provider_to_its_attribute_name() -> None:
    class Base(Group):
        a = providers.Factory(creator=_A)

    class Child(Base):
        b = providers.Factory(creator=_B)

    assert Child.get_named_providers() == {"a": Base.a, "b": Child.b}
    assert list(Child.get_named_providers().items()) == [("b", Child.b), ("a", Base.a)]


def test_get_named_providers_masks_non_provider_override() -> None:
    class Base(Group):
        a = providers.Factory(creator=_A)

    class Child(Base):
        a = "not a provider"

    assert Child.get_named_providers() == {}


def test_get_named_providers_diamond_keeps_single_named_entry() -> None:
    class Base(Group):
        a = providers.Factory(creator=_A)

    class Left(Base): ...

    class Right(Base): ...

    class Diamond(Left, Right): ...

    assert Diamond.get_named_providers() == {"a": Base.a}


def test_get_providers_matches_named_provider_values() -> None:
    class Base(Group):
        a = providers.Factory(creator=_A)

    class Child(Base):
        b = providers.Factory(creator=_B)

    assert Child.get_providers() == list(Child.get_named_providers().values())


class _Svc: ...


class _Ctx: ...


def test_group_scope_stamps_defaulted_providers() -> None:
    class RequestGroup(Group, scope=Scope.REQUEST):
        svc = providers.Factory(_Svc)
        ctx = providers.ContextProvider(_Ctx)

    assert RequestGroup.svc.scope is Scope.REQUEST
    assert RequestGroup.ctx.scope is Scope.REQUEST
    app_container = Container(groups=[RequestGroup], validate=True)
    app_container.open()
    request_container = app_container.build_child_container(scope=Scope.REQUEST)
    request_container.open()
    assert isinstance(request_container.resolve(_Svc), _Svc)


def test_group_scope_explicit_provider_scope_wins() -> None:
    class RequestGroup(Group, scope=Scope.REQUEST):
        app_svc = providers.Factory(_Svc, scope=Scope.APP)

    assert RequestGroup.app_svc.scope is Scope.APP


def test_group_scope_alias_keeps_derived_scope() -> None:
    class RequestGroup(Group, scope=Scope.REQUEST):
        svc = providers.Factory(_Svc)
        alias = providers.Alias(_Svc)

    assert RequestGroup.alias.scope is Scope.APP  # stored scope untouched; effective scope derives from source


def test_group_scope_inherited_by_subclass_body() -> None:
    class RequestGroup(Group, scope=Scope.REQUEST):
        svc = providers.Factory(_Svc)

    class SubGroup(RequestGroup):
        ctx = providers.ContextProvider(_Ctx)

    assert SubGroup.ctx.scope is Scope.REQUEST


def test_group_scope_subclass_kwarg_overrides_inherited_default() -> None:
    class RequestGroup(Group, scope=Scope.REQUEST):
        svc = providers.Factory(_Svc)

    class ActionGroup(RequestGroup, scope=Scope.ACTION):
        deep = providers.Factory(_Ctx)

    assert ActionGroup.deep.scope is Scope.ACTION
    assert RequestGroup.svc.scope is Scope.REQUEST  # parent stamp untouched


def test_group_scope_shared_provider_same_scope_ok() -> None:
    shared = providers.Factory(_Svc)

    class GroupA(Group, scope=Scope.REQUEST):
        svc = shared

    class GroupB(Group, scope=Scope.REQUEST):
        svc = shared

    assert shared.scope is Scope.REQUEST


def test_group_scope_shared_provider_conflicting_scopes_raises() -> None:
    shared = providers.Factory(_Svc)

    class GroupA(Group, scope=Scope.REQUEST):
        svc = shared

    with pytest.raises(GroupScopeConflictError, match=r"GroupA.*GroupB|GroupB.*GroupA") as exc_info:

        class GroupB(Group, scope=Scope.ACTION):
            svc = shared

    assert exc_info.value.first_scope is Scope.REQUEST
    assert exc_info.value.second_scope is Scope.ACTION


def test_group_without_scope_kwarg_keeps_app_default() -> None:
    class PlainGroup(Group):
        svc = providers.Factory(_Svc)

    assert PlainGroup.svc.scope is Scope.APP


def test_group_scope_rejects_non_intenum() -> None:
    with pytest.raises(InvalidScopeTypeError, match="99"):

        class BadGroup(Group, scope=99):  # ty: ignore[invalid-argument-type]
            svc = providers.Factory(_Svc)
