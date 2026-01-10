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


def test_parse_signature() -> None:
    dependency_type, kwargs = parse_signature(int)
    assert dependency_type is int
    assert kwargs == {}

    dependency_type, kwargs = parse_signature(some_function)
    assert dependency_type is int
    assert kwargs == {"arg1": bool, "arg2": str}

    assert parse_signature(async_function)[0] is int
    assert parse_signature(collection_function)[0] is None


async def test_run_methods() -> None:
    assert some_function(arg1=True, arg2="")
    assert await async_function()
    assert collection_function()
