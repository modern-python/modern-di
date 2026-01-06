import dataclasses

from modern_di.helpers.type_helpers import parse_signature


def some_function(arg1: bool, arg2: str) -> int:
    _ = arg1
    _ = arg2
    return 1


async def async_function() -> int:
    return 1


def collection_function() -> list[int]:
    return [1]


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SomeClass:
    arg1: str
    arg2: int


async def test_parse_signature() -> None:
    signature = parse_signature(int)
    assert signature.dependency_type is int
    assert signature.kwargs == {}

    assert some_function(arg1=True, arg2="")
    signature = parse_signature(some_function)
    assert signature.dependency_type is int
    assert signature.kwargs == {"arg1": bool, "arg2": str}

    await async_function()
    assert parse_signature(async_function).dependency_type is int
    collection_function()
    assert parse_signature(collection_function).dependency_type is None
