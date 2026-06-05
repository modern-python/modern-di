import dataclasses

import pytest

from modern_di import Container, Group, providers
from modern_di.exceptions import GroupInstantiationError


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
