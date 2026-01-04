import pytest
from modern_di import Group


def test_group_cannot_be_instantiated() -> None:
    class Dependencies(Group): ...

    with pytest.raises(RuntimeError, match="Dependencies cannot not be instantiated"):
        Dependencies()
