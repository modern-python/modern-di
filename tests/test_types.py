from modern_di import UNSET


def test_unset_repr_names_the_sentinel() -> None:
    assert repr(UNSET) == "UNSET"
