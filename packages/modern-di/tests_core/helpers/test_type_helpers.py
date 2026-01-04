from modern_di.helpers.type_helpers import define_bound_type


def sync_function() -> int:  # pragma: no cover
    return 1


async def async_function() -> int:  # pragma: no cover
    return 1


def collection_function() -> list[int]:  # pragma: no cover
    return [1]


def test_define_bound_type() -> None:
    assert define_bound_type(int) is int
    assert define_bound_type(sync_function) is int
    assert define_bound_type(async_function) is int
    assert define_bound_type(collection_function) is None
