"""Static typing contracts, checked by `ty` in `just lint`; at runtime `assert_type` is a no-op."""

import sys
import types
import typing

import pytest

from modern_di import Container, Group, Scope, exceptions, providers


class _Base:
    closed = False


class _Sub(_Base):
    pool: typing.ClassVar[list[str]] = []


def _make_base() -> _Base:
    return _Base()


def _release_sub(sub: _Sub) -> None:
    sub.pool.clear()


_UserId = typing.NewType("_UserId", int)


def _make_user_id() -> _UserId:
    return _UserId(7)


class _Resource:
    closed = False

    def close(self) -> bool:
        self.closed = True
        return True


class _ResourceGroup(Group):
    resource = providers.Factory(_Resource)


def test_context_provider_without_default_is_typed_as_the_context_type() -> None:
    typing.assert_type(providers.ContextProvider(int), providers.ContextProvider[int])


def test_context_provider_with_a_typed_default_is_typed_as_the_context_type() -> None:
    typing.assert_type(providers.ContextProvider(int, default=0), providers.ContextProvider[int])


def test_context_provider_with_default_none_is_typed_as_optional() -> None:
    provider = providers.ContextProvider(int, default=None, scope=Scope.APP)
    typing.assert_type(provider, providers.ContextProvider[int | None])
    with Container(groups=[]) as container:
        typing.assert_type(container.resolve_provider(provider), int | None)
        assert container.resolve_provider(provider) is None


def test_cache_settings_rejects_a_finalizer_for_a_narrower_type() -> None:
    settings = providers.CacheSettings(finalizer=_release_sub)
    typing.assert_type(settings, providers.CacheSettings[_Sub])
    factory = providers.Factory(_make_base, cache=settings)  # ty: ignore[invalid-argument-type]
    container = Container()
    container.resolve_provider(factory)
    with pytest.raises(exceptions.FinalizerError) as exc_info:
        container.close_sync()
    assert isinstance(exc_info.value.exceptions[0], AttributeError)


def test_cache_settings_accepts_a_finalizer_for_a_wider_type() -> None:
    released: list[object] = []
    settings: providers.CacheSettings[_Base] = providers.CacheSettings(finalizer=released.append)
    factory = providers.Factory(_make_base, cache=providers.CacheSettings(finalizer=released.append))
    typing.assert_type(factory, providers.Factory[_Base])
    with Container() as container:
        instance = container.resolve_provider(providers.Factory(_make_base, cache=settings))
    assert released == [instance]


def test_cache_settings_accepts_a_finalizer_for_the_creator_type() -> None:
    def close_base(base: _Base) -> None:
        base.closed = True

    factory = providers.Factory(_make_base, cache=providers.CacheSettings(finalizer=close_base))
    typing.assert_type(factory, providers.Factory[_Base])
    with Container() as container:
        instance = container.resolve_provider(factory)
    assert instance.closed


def test_newtype_is_accepted_as_a_bound_type() -> None:
    factory = providers.Factory(_make_user_id, bound_type=_UserId)
    alias = providers.Alias(_Base, bound_type=_UserId)
    context_provider = providers.ContextProvider(int, bound_type=_UserId)
    container = Container()
    container.add_providers(factory)
    assert container.resolve(_UserId) == _UserId(7)
    assert container.find_provider(_UserId) is factory
    assert container.resolve_dependency(_UserId) == _UserId(7)
    assert [factory.bound_type, alias.bound_type, context_provider.bound_type] == [_UserId] * 3


def test_resolve_by_class_keeps_the_class_return_type() -> None:
    container = Container()
    container.add_providers(providers.Factory(_make_base))
    typing.assert_type(container.resolve(_Base), _Base)
    typing.assert_type(container.find_provider(_Base), providers.AbstractProvider[_Base] | None)
    typing.assert_type(container.resolve_dependency(_Base), _Base)


if sys.version_info >= (3, 12):
    _Port = typing.TypeAliasType("_Port", int)
    _PORT = 8080

    def test_type_alias_is_accepted_as_a_bound_type() -> None:
        factory = providers.Factory(lambda: _PORT, bound_type=_Port)
        alias = providers.Alias(_Base, bound_type=_Port)
        context_provider = providers.ContextProvider(int, bound_type=_Port)
        container = Container()
        container.add_providers(factory)
        assert container.resolve(_Port) == _PORT
        assert container.find_provider(_Port) is factory
        assert container.resolve_dependency(_Port) == _PORT
        assert [factory.bound_type, alias.bound_type, context_provider.bound_type] == [_Port] * 3


def test_cache_settings_accepts_a_finalizer_that_returns_a_value() -> None:
    settings = providers.CacheSettings(finalizer=_Resource.close)
    typing.assert_type(settings, providers.CacheSettings[_Resource])
    factory = providers.Factory(_Resource, cache=settings)
    with Container() as container:
        instance = container.resolve_provider(factory)
    assert instance.closed


def test_container_accepts_a_tuple_of_groups() -> None:
    container = Container(groups=(_ResourceGroup,))
    assert isinstance(container.resolve(_Resource), _Resource)


def test_container_accepts_a_read_only_context_mapping() -> None:
    context = types.MappingProxyType({str: "given"})
    container = Container(context=context)
    child = container.build_child_container(context=context)
    child.set_context(str, "set")
    assert container.resolve_provider(providers.ContextProvider(str)) == "given"
    assert child.resolve_provider(providers.ContextProvider(str, scope=Scope.SESSION)) == "set"
    assert context[str] == "given"
