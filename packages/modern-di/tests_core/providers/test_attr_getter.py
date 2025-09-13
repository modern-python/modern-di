import typing
from dataclasses import dataclass, field

import pytest
from modern_di import AsyncContainer, Scope, providers


@dataclass
class Nested2:
    some_const = 144


@dataclass
class Nested1:
    nested2_attr: Nested2 = field(default_factory=Nested2)


@dataclass
class Settings:
    some_str_value: str = "some_string_value"
    some_int_value: int = 3453621
    nested1_attr: Nested1 = field(default_factory=Nested1)


async def yield_settings_async() -> typing.AsyncIterator[Settings]:
    yield Settings()


def yield_settings_sync() -> typing.Iterator[Settings]:
    yield Settings()


@dataclass
class NestingTestDTO: ...


@pytest.fixture(
    params=[
        providers.Resource(Scope.APP, yield_settings_sync),
        providers.Singleton(Scope.APP, Settings),
        providers.Object(Scope.APP, Settings()),
        providers.Factory(Scope.APP, Settings),
    ]
)
def some_sync_settings_provider(request: pytest.FixtureRequest) -> providers.AbstractProvider[Settings]:
    return typing.cast(providers.AbstractProvider[Settings], request.param)


@pytest.fixture(
    params=[
        providers.Resource(Scope.APP, yield_settings_async),
    ]
)
def some_async_settings_provider(request: pytest.FixtureRequest) -> providers.AbstractProvider[Settings]:
    return typing.cast(providers.AbstractProvider[Settings], request.param)


@pytest.fixture
async def di_container() -> typing.AsyncIterator[AsyncContainer]:
    di_container_: typing.Final = AsyncContainer()
    async with di_container_:
        yield di_container_


async def test_attr_getter_with_zero_attribute_depth_sync(
    some_sync_settings_provider: providers.AbstractProvider[Settings], di_container: AsyncContainer
) -> None:
    attr_getter = some_sync_settings_provider.some_str_value
    assert await di_container.resolve_provider(attr_getter) == Settings().some_str_value


async def test_attr_getter_with_zero_attribute_depth_async(
    some_async_settings_provider: providers.AbstractProvider[Settings], di_container: AsyncContainer
) -> None:
    attr_getter = some_async_settings_provider.some_str_value
    assert await di_container.resolve_provider(attr_getter) == Settings().some_str_value


async def test_attr_getter_with_more_than_zero_attribute_depth_sync(
    some_sync_settings_provider: providers.AbstractProvider[Settings], di_container: AsyncContainer
) -> None:
    attr_getter = some_sync_settings_provider.nested1_attr.nested2_attr.some_const
    assert await di_container.resolve_provider(attr_getter) == Nested2().some_const


async def test_attr_getter_with_more_than_zero_attribute_depth_async(
    some_async_settings_provider: providers.AbstractProvider[Settings], di_container: AsyncContainer
) -> None:
    attr_getter = some_async_settings_provider.nested1_attr.nested2_attr.some_const
    assert await di_container.resolve_provider(attr_getter) == Nested2().some_const


def test_attr_getter_with_invalid_attribute_sync(
    some_sync_settings_provider: providers.AbstractProvider[Settings],
) -> None:
    with pytest.raises(AttributeError):
        some_sync_settings_provider.nested1_attr.nested2_attr.__some_private__  # noqa: B018
    with pytest.raises(AttributeError):
        some_sync_settings_provider.nested1_attr.__another_private__  # noqa: B018
    with pytest.raises(AttributeError):
        some_sync_settings_provider.nested1_attr._final_private_  # noqa: B018


async def test_attr_getter_with_invalid_attribute_async(
    some_async_settings_provider: providers.AbstractProvider[Settings],
) -> None:
    with pytest.raises(AttributeError):
        some_async_settings_provider.nested1_attr.nested2_attr.__some_private__  # noqa: B018
    with pytest.raises(AttributeError):
        some_async_settings_provider.nested1_attr.__another_private__  # noqa: B018
    with pytest.raises(AttributeError):
        some_async_settings_provider.nested1_attr._final_private_  # noqa: B018
