"""Static typing contracts, checked by `ty` in `just lint`; at runtime `assert_type` is a no-op."""

import typing

import pytest

from modern_di import Container, Scope, exceptions, providers


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


def test_newtype_bound_type_resolves_as_any() -> None:
    factory = providers.Factory(_make_user_id, bound_type=_UserId)
    typing.assert_type(providers.Alias(_Base, bound_type=_UserId), providers.Alias[_Base])
    typing.assert_type(providers.ContextProvider(int, bound_type=_UserId), providers.ContextProvider[int])
    container = Container()
    container.add_providers(factory)
    typing.assert_type(container.resolve(_UserId), typing.Any)
    typing.assert_type(container.find_provider(_UserId), providers.AbstractProvider[typing.Any] | None)
    typing.assert_type(container.resolve_dependency(_UserId), typing.Any)


def test_resolve_by_class_keeps_the_class_type() -> None:
    container = Container()
    container.add_providers(providers.Factory(_make_base))
    typing.assert_type(container.resolve(_Base), _Base)
    typing.assert_type(container.find_provider(_Base), providers.AbstractProvider[_Base] | None)
    typing.assert_type(container.resolve_dependency(_Base), _Base)


def test_cache_settings_accepts_a_finalizer_that_returns_a_value() -> None:
    settings = providers.CacheSettings(finalizer=_Resource.close)
    typing.assert_type(settings, providers.CacheSettings[_Resource])
    factory = providers.Factory(_Resource, cache=settings)
    with Container() as container:
        instance = container.resolve_provider(factory)
    assert instance.closed
