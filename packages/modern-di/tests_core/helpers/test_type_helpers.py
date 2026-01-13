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


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SomeDataClass:
    arg1: str
    arg2: int


@dataclasses.dataclass(kw_only=True, slots=True)
class SomeDataClassInitFalse:
    arg1: str
    arg2: int = dataclasses.field(init=False)


class SomeRegularClass:
    def __init__(self, arg1: str, arg2: int) -> None: ...


def test_parse_signature_for_regular_class() -> None:
    # Test with dataclass
    dependency_type, kwargs = parse_signature(SomeDataClass)
    assert dependency_type is SomeDataClass
    assert kwargs == {"arg1": str, "arg2": int}

    dependency_type, kwargs = parse_signature(SomeDataClassInitFalse)
    assert dependency_type is SomeDataClassInitFalse
    # arg2 should not be in kwargs because it has init=False
    assert kwargs == {"arg1": str}

    # Test with regular class
    dependency_type, kwargs = parse_signature(SomeRegularClass)
    assert dependency_type is SomeRegularClass
    assert kwargs == {"arg1": str, "arg2": int}
