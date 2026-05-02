import pytest

from modern_di import Group
from modern_di.exceptions import GroupInstantiationError


def test_group_cannot_be_instantiated() -> None:
    class Dependencies(Group): ...

    with pytest.raises(GroupInstantiationError, match="Dependencies cannot be instantiated") as exc:
        Dependencies()
    assert exc.value.group_name == "Dependencies"
