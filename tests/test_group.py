import dataclasses

import pytest

from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import DuplicateProviderTypeError, GroupInstantiationError


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
    assert isinstance(container.resolve(_A), _A)
    assert isinstance(container.resolve(_B), _B)


def test_group_subclass_overrides_parent_provider() -> None:
    class Base(Group):
        a = providers.Factory(creator=_A)

    class Child(Base):
        a = providers.Factory(creator=_A, bound_type=_B)  # override; resolve _B yields _A instance

    container = Container(groups=[Child])
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
