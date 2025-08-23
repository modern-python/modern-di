import typing

from modern_di.helpers.type_helpers import define_bounded_type


def sync_function() -> int:  # pragma: no cover
    return 1


async def async_function() -> int:  # pragma: no cover
    return 1


def generator() -> typing.Iterator[int]:  # pragma: no cover
    yield 1


async def async_generator() -> typing.AsyncIterator[int]:  # pragma: no cover
    yield 1


def collection_function() -> list[int]:  # pragma: no cover
    return [1]


def generator_without_args() -> typing.Iterator:  # type: ignore[type-arg]  # pragma: no cover
    yield 1


def test_define_bounded_type() -> None:
    assert define_bounded_type(int) is int
    assert define_bounded_type(sync_function) is int
    assert define_bounded_type(async_function) is int
    assert define_bounded_type(generator) is int
    assert define_bounded_type(async_generator) is int
    assert define_bounded_type(collection_function) is None
    assert define_bounded_type(generator_without_args) is None
